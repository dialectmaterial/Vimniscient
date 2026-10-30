//! How a task went.

use super::lessons::Task;

#[derive(Clone, Debug, Default)]
pub struct TaskResult {
    pub task: Task,
    pub status: String, // solved | failed (endless) | skipped | quit | unseen
    pub keys: String,
    pub count: usize,
    pub hints: usize,
    pub level: usize, // endless mode: the level the task was given at
    pub budget: Option<usize>, // endless mode: the most keys allowed
    pub seconds: Option<f64>, // from the task appearing to it ending; None when not timed
    pub first: Option<f64>, // before the first key
}

impl TaskResult {
    pub fn new(task: &Task, status: &str, keys: &str, count: usize, hints: usize) -> TaskResult {
        TaskResult { task: task.clone(), status: status.into(), keys: keys.into(), count, hints, ..TaskResult::default() }
    }
}
