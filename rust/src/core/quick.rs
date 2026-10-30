//! Quick practice: a minute or two on one skill, whenever there's time. Tasks come
//! from the lessons you've done, on any of their texts, or for navigation from the
//! generators. Like Endless, it counts for the streak and grades nothing.

use super::generate::Rng;
use super::lessons::{Lesson, SKILLS, Task};
use super::srs::round_half_even;
use indexmap::IndexMap;
use std::collections::HashSet;

pub const DEFAULT_MINUTES: u32 = 2;
const TASK_SECONDS: f64 = 12.0; // until there's a timed history to go by
pub const NAVIGATION: &str = "navigation";
pub const ANY: &str = "any";
const NAV_KINDS: [&str; 3] = ["nav-down", "nav-up", "nav-find"];

pub fn title(skill: &str) -> String {
    match skill {
        NAVIGATION => "Navigation".into(),
        ANY => "Any skill".into(),
        "text-objects" => "Text objects".into(),
        "ex" => "Ex commands".into(),
        other => {
            let mut letters = other.chars();
            letters.next().map(|c| c.to_uppercase().chain(letters).collect()).unwrap_or_default()
        }
    }
}

/// The tasks each skill can draw on, skills with nothing done yet left out.
pub fn pools(lessons: &[Lesson], done: &HashSet<String>) -> IndexMap<String, Vec<Task>> {
    let finished: Vec<&Lesson> = lessons.iter().filter(|l| done.contains(&l.id)).collect();
    let mut found = IndexMap::new();
    found.insert(ANY.to_string(), finished.iter().flat_map(|l| l.tasks.iter().cloned()).collect::<Vec<_>>());
    for skill in SKILLS {
        found.insert(skill.to_string(), finished.iter().filter(|l| l.skill == skill).flat_map(|l| l.tasks.iter().cloned()).collect());
    }
    found.retain(|_, tasks| !tasks.is_empty());
    found
}

pub fn how_many(minutes: u32, typical: Option<f64>) -> usize {
    round_half_even(f64::from(minutes) * 60.0 / typical.unwrap_or(TASK_SECONDS)).max(2) as usize
}

pub fn navigation(count: usize, parent: &Task, seed: &str) -> Vec<Task> {
    let mut rng = Rng::new(&format!("nav:{seed}"));
    (0..count).map(|n| parent.generate_kind(rng.choice(&NAV_KINDS), &format!("{seed}:{n}"))).collect()
}

/// `count` tasks from `pool`, each on a random text; repeats only once all have come up.
pub fn tasks(pool: &[Task], count: usize, seed: &str) -> Vec<Task> {
    let mut rng = Rng::new(&format!("quick:{seed}"));
    let mut order: Vec<Task> = Vec::new();
    while order.len() < count {
        let mut round = pool.to_vec();
        rng.shuffle(&mut round);
        order.extend(round);
    }
    order.truncate(count);
    order.iter().enumerate().map(|(n, t)| t.choice(rng.below(t.choices()), &format!("{}:{seed}:{n}", t.item_id()))).collect()
}

pub fn build(skill: &str, count: usize, found: &IndexMap<String, Vec<Task>>, parent: &Task, seed: &str) -> Vec<Task> {
    if skill == NAVIGATION { navigation(count, parent, seed) } else { tasks(&found[skill], count, seed) }
}
