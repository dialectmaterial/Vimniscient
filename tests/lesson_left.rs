//! A lesson begun but not done runs only the tasks not recalled yet.

mod common;

use vimniscient::core::lessons::{LESSONS, two_rounds};
use vimniscient::core::progress::Progress;
use vimniscient::core::results::TaskResult;

#[test]
fn a_begun_lesson_runs_what_is_left() {
    let dir = std::env::temp_dir().join(format!("vimniscient-lesson-left-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    // SAFETY: this binary has one test; environment setup precedes all readers.
    unsafe {
        std::env::set_var("HOME", &dir);
        std::env::set_var("VIMNISCIENT_DATA", dir.join("data"));
        std::env::set_var("XDG_CONFIG_HOME", dir.join("config"));
        std::env::set_var("XDG_STATE_HOME", dir.join("state"));
    }
    common::fake_machine(&dir);
    let progress = Progress::open().unwrap();
    let lesson = LESSONS.iter().find(|l| l.id == "w2d3-cgn").unwrap();
    assert_eq!(progress.left(lesson).tasks.len(), lesson.tasks.len(), "not begun: the whole lesson");

    // a Learn solve doesn't count; a Recall solve of task 1 does
    let task = &lesson.tasks[1];
    let solve = |phase: &str| TaskResult::new(&task.as_phase(phase), "solved", "*Ncgna<Esc>nn.", 10, 0);
    progress.record(&[solve("learn")]);
    assert_eq!(progress.left(lesson).tasks.len(), lesson.tasks.len());
    progress.record(&[solve("recall")]);
    let left = progress.left(lesson);
    assert_eq!(left.tasks.iter().map(|t| t.index).collect::<Vec<_>>(), vec![0, 2, 3, 4]);
    let session = two_rounds(&left, "2026-11-15");
    assert_eq!(session.len(), 8, "Learn and Recall for the four left");
    assert!(session.iter().all(|t| t.index != 1));

    // once every task is recalled, the lesson runs whole again for practice
    for t in &lesson.tasks {
        progress.record(&[TaskResult::new(&t.as_phase("recall"), "solved", &t.solution, t.reference(), 1)]);
    }
    assert!(progress.is_done(lesson));
    assert_eq!(progress.left(lesson).tasks.len(), lesson.tasks.len());
    let _ = std::fs::remove_dir_all(&dir);
}
