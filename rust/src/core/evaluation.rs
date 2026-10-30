//! `vimniscient eval`: does the training work? Three sittings of the same eight skills,
//! on texts from no lesson, with no hints: `pre` now, `post` after some weeks of
//! training, `delayed` a few weeks after that. Stored locally, never graded.

use super::lessons::{Lesson, Task};
use super::progress::Progress;
use super::{content, transfer::hidden_task};
use serde_norway::Value;

pub const LESSON_ID: &str = "eval";
const HINT: &str = "No hints in the test: :Skip what you don't know.";
pub const STAGES: [&str; 3] = ["pre", "post", "delayed"];

fn form(stage: &str) -> &'static str {
    if stage == "post" { "b" } else { "a" }
}

pub fn tasks(stage: &str) -> Vec<(Task, Vec<String>)> {
    let data: Value = serde_norway::from_str(&content::text("eval.yaml")).expect("eval.yaml");
    data["forms"][form(stage)].as_sequence().expect("a form").iter().enumerate().map(|(i, t)| hidden_task(t, LESSON_ID, i, HINT)).collect()
}

pub fn lesson(stage: &str) -> Lesson {
    Lesson { id: LESSON_ID.into(), title: format!("Evaluation: {stage}"), skill: "mixed".into(), tasks: tasks(stage).into_iter().map(|(t, _)| t).collect(), ..Lesson::default() }
}

fn median(mut values: Vec<f64>) -> f64 {
    values.sort_by(f64::total_cmp);
    let mid = values.len() / 2;
    if values.len() % 2 == 1 { values[mid] } else { (values[mid - 1] + values[mid]) / 2.0 }
}

pub fn report(progress: &Progress) -> String {
    let mut lines = vec![format!("{:8}{:12}{:8}{:9}keys/ref", "", "date", "solved", "median")];
    for stage in STAGES {
        let sql = "SELECT status, seconds, count, ref, ts FROM attempts WHERE phase = ? ORDER BY id DESC LIMIT ?";
        let size = tasks(stage).len();
        let rows: Vec<(String, Option<f64>, f64, f64, String)> = progress.db.prepare(sql).ok().and_then(|mut statement| {
            statement.query_map(rusqlite::params![format!("eval-{stage}"), size], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)))
                .ok().map(|found| found.flatten().collect())
        }).unwrap_or_default();
        let Some(first) = rows.first() else {
            lines.push(format!("{stage:8}not taken yet: vimniscient eval {stage}"));
            continue;
        };
        let solved: Vec<_> = rows.iter().filter(|r| r.0 == "solved").collect();
        let seconds: Vec<f64> = solved.iter().filter_map(|r| r.1).collect();
        let time = if seconds.is_empty() { "-".to_string() } else { format!("{:.1}s", median(seconds)) };
        let reference: f64 = solved.iter().map(|r| r.3).sum();
        let ratio = if solved.is_empty() { "-".to_string() } else { format!("{:.2}", solved.iter().map(|r| r.2).sum::<f64>() / reference) };
        lines.push(format!("{stage:8}{:12}{:8}{time:9}{ratio}", &first.4[..10], format!("{}/{}", solved.len(), rows.len())));
    }
    lines.join("\n")
}
