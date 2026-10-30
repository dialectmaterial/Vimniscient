//! Endless mode: tasks from every lesson, one after another, getting harder. Each task
//! you solve climbs a level; new lessons join the mix and the key budget shrinks to
//! exactly the reference by level RAMP (the runner works it out, see runner.lua).

use super::generate::Rng;
use super::lessons::{Lesson, Task};
use super::progress::Run;
use super::results::TaskResult;
use std::collections::VecDeque;

const LEVELS_PER_LESSON: usize = 4;
pub const RAMP: usize = 200;
pub const GAP: usize = 2;
const RUNGS: usize = 1000; // more than anyone climbs in a sitting; the runner wraps around after
pub const RESTART_BELOW: usize = 10; // a new run starts this many levels below where the last one ended

/// How many lessons are in the mix at `level`.
pub fn unlocked(level: usize, lessons: usize) -> usize {
    (1 + (level - 1) / LEVELS_PER_LESSON).min(lessons).max(1)
}

/// The tasks to climb from level `start` on, as (task, version).
pub fn ladder(lessons: &[Lesson], start: usize, seed: &str) -> Vec<(Task, usize)> {
    let mut rng = Rng::new(seed);
    let mut recent: VecDeque<String> = VecDeque::new();
    let mut rungs = Vec::with_capacity(RUNGS);
    for level in start..start + RUNGS {
        let mix = &lessons[..unlocked(level, lessons.len())];
        let lesson = if rng.coin() { &mix[mix.len() - 1] } else { rng.choice(mix) };
        let fresh: Vec<&Task> = lesson.tasks.iter().filter(|t| !recent.contains(&t.item_id())).collect();
        let task = if fresh.is_empty() { rng.choice(&lesson.tasks) } else { *rng.choice(&fresh) };
        recent.push_back(task.item_id());
        if recent.len() > 8 {
            recent.pop_front();
        }
        rungs.push((task.clone(), rng.below(task.choices())));
    }
    rungs
}

pub fn note(run: &Run, best: usize) -> String {
    let misses = format!("{} {}", run.missed, if run.missed == 1 { "miss" } else { "misses" });
    let text = format!("Level {} → {} · {misses}, {} recalled afterwards", run.start, run.level, run.fixed);
    if run.level > best && run.climbed > 0 { format!("{text} · a new best!") } else { text }
}

pub fn summary(results: &[TaskResult], start: usize) -> Run {
    let climbed = results.iter().filter(|r| r.task.phase == "climb" && r.status == "solved").count();
    Run {
        start,
        level: start + climbed,
        climbed,
        missed: results.iter().filter(|r| matches!(r.status.as_str(), "failed" | "skipped") && r.task.phase != "learn").count(),
        fixed: results.iter().filter(|r| r.task.phase == "recall" && r.status == "solved").count(),
    }
}
