//! Choose: edits with no hint, where you pick the strategy (see transfer.yaml). Several
//! solutions count, and the results show another way without rejecting yours. Like
//! Endless it counts for the streak and grades nothing.

use super::lessons::{Task, parse_start};
use super::{content, keys::count_keys, lessons::Lesson, progress::Progress, results::TaskResult};
use serde_norway::Value;
use std::collections::HashSet;
use std::sync::LazyLock;

pub const LESSON_ID: &str = "transfer";
pub const PER_RUN: usize = 4;
const HINT: &str = "No hints here: choosing the keys is the exercise. :Skip shows ways to do it on the results.";

#[derive(Clone, Debug)]
pub struct Challenge {
    pub after: String, // the lesson that unlocks it
    pub task: Task,
    pub ways: Vec<String>,
}

/// A hint-free task from YAML: a solution of "—" keeps the runner from giving anything
/// away, as in VimGolf.
pub fn hidden_task(t: &Value, lesson_id: &str, index: usize, hint: &str) -> (Task, Vec<String>) {
    let (start, cursor) = parse_start(&content::scalar(&t["start"]));
    let ways: Vec<String> = t["ways"].as_sequence().expect("ways").iter().map(content::scalar).collect();
    let task = Task {
        goal: content::scalar(&t["goal"]),
        start,
        cursor,
        target: content::scalar(&t["target"]).split('\n').map(str::to_string).collect(),
        solution: "—".into(),
        hint: hint.into(),
        lesson_id: lesson_id.into(),
        index,
        ref_override: ways.iter().map(|way| count_keys(way)).min(),
        phase: "recall".into(),
        ..Task::default()
    };
    (task, ways)
}

pub static CHALLENGES: LazyLock<Vec<Challenge>> = LazyLock::new(|| {
    let data: Value = serde_norway::from_str(&content::text("transfer.yaml")).expect("transfer.yaml");
    data["tasks"].as_sequence().expect("tasks").iter().enumerate().map(|(index, t)| {
        let (task, ways) = hidden_task(t, LESSON_ID, index, HINT);
        Challenge { after: content::scalar(&t["after"]), task, ways }
    }).collect()
});

pub fn unlocked(done: &HashSet<String>) -> Vec<Challenge> {
    CHALLENGES.iter().filter(|c| done.contains(&c.after)).cloned().collect()
}

/// The unlocked tasks you've gone longest without, never-tried ones first.
pub fn pick(lessons: &[Lesson], progress: &Progress) -> Vec<Challenge> {
    let mut open = unlocked(&progress.done(lessons));
    let last = progress.last_tried("transfer");
    open.sort_by_key(|c| last.get(&c.task.index).cloned().unwrap_or_default());
    open.truncate(PER_RUN);
    open
}

/// The ways worth showing after a try: another one, or all of them after a skip.
pub fn another_way(challenge: &Challenge, keys: &str, solved: bool) -> Vec<String> {
    if !solved {
        return challenge.ways.clone();
    }
    challenge.ways.iter().filter(|way| *way != keys).take(1).cloned().collect()
}

/// What the results say after a run: another way for each task.
pub fn note(picks: &[Challenge], results: &[TaskResult]) -> String {
    let lines: Vec<String> = results.iter().filter_map(|r| {
        let challenge = picks.iter().find(|c| c.task.goal == r.task.goal)?;
        let ways = another_way(challenge, &r.keys, r.status == "solved");
        (!ways.is_empty()).then(|| format!("{}  {}", r.task.goal, ways.join("  or  ")))
    }).collect();
    if lines.is_empty() { String::new() } else { format!("Another way\n{}", lines.join("\n")) }
}
