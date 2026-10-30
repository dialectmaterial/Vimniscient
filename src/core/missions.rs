//! Multi-file missions (missions.yaml): real files in a throwaway folder, your own
//! Neovim with all its plugins, and a check that runs when you save. Ungraded.

use super::lessons::{Lesson, Task};
use super::{content, keys::count_keys, progress::Progress};
use indexmap::IndexMap;
use serde_norway::Value;
use std::sync::LazyLock;

pub const LESSON_ID: &str = "mission";

#[derive(Clone, Debug)]
pub struct Mission {
    pub index: usize,
    pub after: String,
    pub title: String,
    pub goal: String,
    pub hint: String,
    pub files: IndexMap<String, String>,
    pub targets: IndexMap<String, String>,
    pub ways: Vec<String>,
}

impl Mission {
    pub fn note(&self, solved: bool) -> String {
        format!("{}\n{}", if solved { "Another way" } else { "Ways to do it" }, self.ways.join("\n"))
    }

    pub fn task(&self) -> Task {
        Task {
            goal: self.goal.clone(),
            start: vec![String::new()],
            cursor: (1, 0),
            target: vec![String::new()],
            solution: "—".into(),
            hint: self.hint.clone(),
            lesson_id: LESSON_ID.into(),
            index: self.index,
            ref_override: self.ways.iter().map(|way| count_keys(way)).min(),
            phase: "recall".into(),
            ..Task::default()
        }
    }
}

fn texts(value: &Value) -> IndexMap<String, String> {
    value.as_mapping().expect("files").iter().map(|(name, text)| (content::scalar(name), content::scalar(text))).collect()
}

pub static MISSIONS: LazyLock<Vec<Mission>> = LazyLock::new(|| {
    let data: Value = serde_norway::from_str(&content::text("missions.yaml")).expect("missions.yaml");
    data["missions"].as_sequence().expect("missions").iter().enumerate().map(|(index, m)| Mission {
        index,
        after: content::scalar(&m["after"]),
        title: content::scalar(&m["title"]),
        goal: content::scalar(&m["goal"]),
        hint: content::scalar(&m["hint"]),
        files: texts(&m["files"]),
        targets: texts(&m["targets"]),
        ways: m["ways"].as_sequence().expect("ways").iter().map(content::scalar).collect(),
    }).collect()
});

/// The unlocked mission you've gone longest without, never-tried ones first.
pub fn pick(lessons: &[Lesson], progress: &Progress) -> Option<Mission> {
    let done = progress.done(lessons);
    let last = progress.last_tried("mission");
    MISSIONS.iter().filter(|m| done.contains(&m.after)).min_by_key(|m| last.get(&m.index).cloned().unwrap_or_default()).cloned()
}
