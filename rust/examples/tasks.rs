//! Tasks as JSON for tests. `generated`: 150 seeds of every kind, for check_lessons.lua.
//! `plan <lesson>`: what `vimniscient run` gives today, in order, with the keys.
//! `mission`: plays the first mission. `endless <seed>`: the first rungs.

use serde_json::json;
use vimniscient::core::lessons::{LESSONS, two_rounds};
use vimniscient::core::{endless, generate, missions, progress::{Progress, today}};
use vimniscient::system::nvim;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args[0].as_str() {
        "generated" => {
            let parent = &LESSONS[0].tasks[0];
            let mut tasks = Vec::new();
            for kind in generate::KINDS {
                for n in 0..150 {
                    let t = generate::generate(kind, &n.to_string(), parent);
                    tasks.push(json!({"id": format!("{kind} seed {n}"), "goal": t.goal, "start": t.start, "cursor": [t.cursor.0, t.cursor.1], "target": t.target, "solution": t.solution, "ft": t.ft}));
                }
            }
            println!("{}", json!(tasks));
        }
        "plan" => {
            let lesson = LESSONS.iter().find(|l| l.id == args[1]).unwrap();
            let tasks: Vec<_> = two_rounds(lesson, &today().to_string()).iter().map(|t| json!({"goal": t.goal, "solution": t.solution, "phase": t.phase})).collect();
            println!("{}", json!(tasks));
        }
        "mission" => {
            let result = nvim::run_mission(&missions::MISSIONS[0]);
            Progress::open().unwrap().record_ungraded(&[result], "mission");
        }
        "endless" => {
            let open: Vec<_> = LESSONS.iter().filter(|l| !l.lazyvim || vimniscient::core::cards::has_lazyvim()).cloned().collect();
            let rungs = endless::ladder(&open, 1, &args[1]);
            let tasks: Vec<_> = rungs.iter().take(6).map(|(t, v)| { let c = t.choice(*v, &format!("{}:{}", t.item_id(), today())); json!({"solution": c.solution, "goal": c.goal}) }).collect();
            println!("{}", json!(tasks));
        }
        _ => {}
    }
}
