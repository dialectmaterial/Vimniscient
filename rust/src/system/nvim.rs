//! Running tasks in Neovim: the session as JSON for runner.lua, and the results it writes.

use crate::core::lessons::{Lesson, Task};
use crate::core::missions::Mission;
use crate::core::mnemonics::hooks;
use crate::core::progress::today;
use crate::core::{content, results::TaskResult};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::io::{IsTerminal, Write};
use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering};

/// The theme's colours as hex, for lessons in Neovim to draw with. The interface fills it.
pub static COLORS: Mutex<Option<Value>> = Mutex::new(None);

/// With the mouse off, terminals like foot turn the wheel into arrow keys (DECSET 1007):
/// it would scroll lists, and type arrows into lessons. Off while Vimniscient runs,
/// Neovim included; back on when it quits.
pub fn mouse_wheel(on: bool) {
    let mut out = std::io::stdout();
    if out.is_terminal() {
        let _ = out.write_all(if on { b"\x1b[?1007h" } else { b"\x1b[?1007l" });
        let _ = out.flush();
    }
}

/// A folder of our own for one run, gone when it's dropped.
struct Scratch(PathBuf);

impl Scratch {
    fn new() -> std::io::Result<Scratch> {
        static COUNT: AtomicUsize = AtomicUsize::new(0);
        let name = format!("vimniscient-{}-{}", std::process::id(), COUNT.fetch_add(1, Ordering::Relaxed));
        let path = std::env::temp_dir().join(name);
        std::fs::create_dir_all(&path)?;
        Ok(Scratch(path))
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn task_json(t: &Task) -> Value {
    json!({
        "goal": t.goal, "start": t.start, "cursor": [t.cursor.0, t.cursor.1], "target": t.target, "ref": t.reference(),
        "hint": t.hint, "solution": t.solution, "ft": t.ft, "phase": t.phase,
        "why": if t.solution == "—" { Vec::new() } else { hooks(&t.solution) }, // what the keys stand for
    })
}

/// Start Neovim with the runner on `session`; returns the raw results it wrote.
fn run_nvim(mut session: Value, first: &[String]) -> Vec<Value> {
    let Ok(tmp) = Scratch::new() else { return Vec::new() };
    let (session_path, result_path, practice, runner) = (tmp.0.join("session.json"), tmp.0.join("results.json"), tmp.0.join("practice.txt"), tmp.0.join("runner.lua"));
    let colors = COLORS.lock().ok().and_then(|c| c.clone());
    session["result_path"] = json!(result_path);
    session["colors"] = colors.unwrap_or(Value::Null);
    let written = std::fs::write(&practice, first.join("\n")).and(std::fs::write(&session_path, session.to_string())).and(std::fs::write(&runner, content::text("nvim/runner.lua")));
    if written.is_err() {
        return Vec::new();
    }
    // the working folder keeps session plugins away from your real projects;
    // -i NONE gives every lesson clean registers and history.
    mouse_wheel(false);
    let _ = Command::new("nvim").args(["-i", "NONE"]).arg(&practice).arg("-S").arg(&runner).current_dir(&tmp.0).env("VIMNISCIENT_SESSION", &session_path).status();
    mouse_wheel(true);
    std::fs::read_to_string(&result_path).ok().and_then(|text| serde_json::from_str(&text).ok()).unwrap_or_default()
}

fn text(r: &Value, key: &str) -> String {
    r[key].as_str().unwrap_or_default().to_string()
}

fn number(r: &Value, key: &str) -> usize {
    r[key].as_u64().unwrap_or(0) as usize
}

fn result(task: Task, r: &Value, unseen: &str) -> TaskResult {
    TaskResult {
        task,
        status: r["status"].as_str().unwrap_or(unseen).to_string(),
        keys: text(r, "keys"),
        count: number(r, "count"),
        hints: number(r, "hints"),
        level: number(r, "level"),
        budget: r["budget"].as_u64().map(|b| b as usize),
        seconds: r["seconds"].as_f64(),
        first: r["first"].as_f64(),
    }
}

/// With `retry`, a skipped Recall task is shown, typed once with the keys shown, and
/// asked again on its next text at the end (see runner.lua).
pub fn run_lesson(lesson: &Lesson, retry: bool) -> Vec<TaskResult> {
    let total = |phase: &str| lesson.tasks.iter().filter(|t| t.phase == phase).count();
    let (learn, recall) = (total("learn"), total("recall"));
    let mut seen: HashMap<&str, usize> = HashMap::new();
    let mut tasks = Vec::new();
    for (n, t) in lesson.tasks.iter().enumerate() {
        let count = seen.entry(&t.phase).or_default();
        *count += 1;
        let of = if t.phase == "learn" { learn } else { recall };
        let mut task = task_json(t);
        task["n"] = json!(n);
        task["label"] = if learn > 0 { json!(format!("{} {}/{of}", t.phase.to_uppercase(), *count)) } else { Value::Null };
        task["show"] = json!(if t.phase == "learn" { t.solution.as_str() } else { "" });
        if retry && t.phase == "recall" {
            task["again"] = task_json(&t.next_version());
        }
        tasks.push(task);
    }
    let title = if lesson.week > 0 { format!("{} · {}", lesson.label(), lesson.title) } else { lesson.title.clone() };
    let mut raw = run_nvim(json!({"title": title, "tasks": tasks, "retry": retry}), &lesson.tasks[0].start);
    if raw.is_empty() {
        raw = (0..lesson.tasks.len()).map(|n| json!({"n": n})).collect(); // Neovim never got going: every task unseen
    }
    raw.iter().map(|r| {
        let task = &lesson.tasks[number(r, "n")];
        let task = match r["extra"].as_str() {
            Some("learn") => task.as_phase("learn"),
            Some("recall") => task.next_version().as_phase("recall"),
            _ => task.clone(),
        };
        result(task, r, "unseen")
    }).collect()
}

/// Endless mode: the runner climbs `rungs` (task, version) from `level` on, and slots in
/// a Learn and a Recall for every task missed (see endless.rs).
pub fn run_endless(rungs: &[(Task, usize)], level: usize, ramp: usize, gap: usize) -> Vec<TaskResult> {
    let day = today();
    let pool: HashMap<String, &Task> = rungs.iter().map(|(t, _)| (t.item_id(), t)).collect();
    let seed = |id: &str| format!("{id}:{day}"); // a task's generated text is new each day, and the same all run
    let texts: serde_json::Map<String, Value> = pool.iter().map(|(id, t)| {
        (id.clone(), Value::Array((0..t.choices()).map(|v| task_json(&t.choice(v, &seed(id)))).collect()))
    }).collect();
    let steps: Vec<Value> = rungs.iter().map(|(t, v)| json!({"id": t.item_id(), "v": v})).collect();
    let session = json!({"title": "Endless", "tasks": [], "endless": {"pool": texts, "rungs": steps, "level": level, "ramp": ramp, "gap": gap}});
    let (first, v) = &rungs[0];
    run_nvim(session, &first.choice(*v, &seed(&first.item_id())).start).iter().filter_map(|r| {
        let id = r["id"].as_str()?;
        let task = pool.get(id).filter(|_| r["status"] != "unseen")?;
        let phase = text(r, "phase");
        Some(result(task.choice(number(r, "v"), &seed(id)).as_phase(&phase), r, "unseen"))
    }).collect()
}

/// A mission in your own Neovim, on throwaway files in a folder of their own.
pub fn run_mission(mission: &Mission) -> TaskResult {
    let task = mission.task();
    let run = || -> std::io::Result<Value> {
        let tmp = Scratch::new()?;
        let work = tmp.0.join("project"); // the session file stays out of the project your plugins see
        std::fs::create_dir_all(&work)?;
        for (name, text) in &mission.files {
            std::fs::write(work.join(name), text)?;
        }
        let (result_path, session_path, script) = (tmp.0.join("result.json"), tmp.0.join("session.json"), tmp.0.join("mission.lua"));
        let targets: serde_json::Map<String, Value> = mission.targets.iter().map(|(name, text)| (name.clone(), json!(text.lines().collect::<Vec<_>>()))).collect();
        std::fs::write(&session_path, json!({"goal": mission.goal, "hint": mission.hint, "result_path": result_path, "targets": targets}).to_string())?;
        std::fs::write(&script, content::text("nvim/mission.lua"))?;
        mouse_wheel(false);
        let first = mission.files.keys().next().cloned().unwrap_or_default();
        let _ = Command::new("nvim").args(["-i", "NONE"]).arg(first).arg("-S").arg(&script).current_dir(&work).env("VIMNISCIENT_MISSION", &session_path).status();
        mouse_wheel(true);
        let text = std::fs::read_to_string(&result_path)?;
        Ok(serde_json::from_str(&text).unwrap_or_default())
    };
    let raw = run().unwrap_or_default();
    result(task, &raw, "quit")
}
