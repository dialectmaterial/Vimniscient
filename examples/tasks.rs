//! Tasks as JSON for tests/check_neovim.py and tests/live.py.
//! `written`: every lesson text; `lazyvim` for the LazyVim lessons. `generated`: 150 seeds of
//! every kind. `ways`: every Choose and eval way. `missions`: their files and ways.
//! `plan <lesson>`: what `vimniscient run` gives today, with the keys. `endless <seed>`: the
//! first rungs. `mission`: plays the first mission.

use serde_json::{Value, json};
use vimniscient::core::lessons::{LESSONS, Task, two_rounds};
use vimniscient::core::{cards, endless, evaluation, generate, missions, progress::{Progress, today}, transfer};
use vimniscient::system::nvim;

fn row(id: String, t: &Task, solution: &str) -> Value {
    json!({"id": id, "goal": t.goal, "start": t.start, "cursor": [t.cursor.0, t.cursor.1], "target": t.target, "solution": solution, "ft": t.ft})
}

fn written(lazyvim: bool) -> Vec<Value> {
    LESSONS.iter().filter(|l| l.lazyvim == lazyvim).flat_map(|l| l.tasks.iter().flat_map(move |t| {
        t.siblings.iter().enumerate().map(move |(n, v)| row(format!("{}#{} (version {n})", l.id, t.index + 1), v, &v.solution))
    })).collect()
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let out = match args[0].as_str() {
        "written" => json!(written(false)),
        "lazyvim" => json!(written(true)),
        "generated" => {
            let parent = &LESSONS[0].tasks[0];
            json!(generate::KINDS.iter().flat_map(|kind| (0..150).map(move |n| {
                let t = generate::generate(kind, &n.to_string(), parent);
                row(format!("{kind} seed {n}"), &t, &t.solution)
            })).collect::<Vec<_>>())
        }
        "ways" => {
            let mut tasks: Vec<Value> = transfer::CHALLENGES.iter().flat_map(|c| c.ways.iter().map(|way| row(format!("choose {}: {way}", c.task.index), &c.task, way))).collect();
            for stage in ["pre", "post"] {
                for (task, ways) in evaluation::tasks(stage) {
                    tasks.extend(ways.iter().map(|way| row(format!("eval {stage} {}: {way}", task.index), &task, way)));
                }
            }
            json!(tasks)
        }
        "missions" => json!(missions::MISSIONS.iter().map(|m| json!({"title": m.title, "files": m.files, "targets": m.targets, "ways": m.ways})).collect::<Vec<_>>()),
        "plan" => {
            let lesson = LESSONS.iter().find(|l| l.id == args[1]).unwrap();
            json!(two_rounds(lesson, &today().to_string()).iter().map(|t| json!({"solution": t.solution, "phase": t.phase, "again": t.next_version().solution})).collect::<Vec<_>>())
        }
        "endless" => {
            let open: Vec<_> = LESSONS.iter().filter(|l| !l.lazyvim || cards::has_lazyvim()).cloned().collect();
            let rungs = endless::ladder(&open, 1, &args[1]);
            json!(rungs.iter().take(6).map(|(t, v)| json!({"solution": t.choice(*v, &format!("{}:{}", t.item_id(), today())).solution})).collect::<Vec<_>>())
        }
        "mission" => {
            let result = nvim::run_mission(&missions::MISSIONS[0]);
            Progress::open().unwrap().record_ungraded(&[result], "mission");
            return;
        }
        _ => return,
    };
    println!("{out}");
}
