//! What every lesson, Choose task, mission and eval form has to be.

use std::collections::HashSet;
use vimniscient::core::lessons::{LESSONS, SKILLS};
use vimniscient::core::{diagnose::diagnose, evaluation, generate, missions, quick, transfer};

#[test]
fn lessons_are_well_formed() {
    assert_eq!(LESSONS.len(), 37);
    for lesson in LESSONS.iter() {
        assert!(SKILLS.contains(&lesson.skill.as_str()), "{}", lesson.id);
        assert!(!lesson.review || lesson.skill == "mixed", "{}", lesson.id);
        for task in &lesson.tasks {
            assert!(task.versions() >= 2, "{} has one text", task.item_id());
            assert!(task.generator.is_empty() || generate::KINDS.contains(&task.generator.as_str()), "{}", task.generator);
            for version in task.siblings.iter() {
                assert_ne!(version.start, version.target, "{} starts solved", task.item_id());
            }
        }
    }
}

#[test]
fn no_reference_solution_sets_off_the_feedback() {
    let parent = &LESSONS[0].tasks[0];
    let written = LESSONS.iter().flat_map(|l| &l.tasks).flat_map(|t| t.siblings.iter().cloned());
    let generated = generate::KINDS.iter().flat_map(|kind| (0..60).map(move |n| generate::generate(kind, &n.to_string(), parent)));
    for task in written.chain(generated) {
        assert_eq!(diagnose(&task.solution, task.reference() + 1, task.reference()), "", "{}", task.solution);
    }
}

#[test]
fn choose_missions_and_the_eval_have_their_ways() {
    let ids: HashSet<&str> = LESSONS.iter().map(|l| l.id.as_str()).collect();
    for challenge in transfer::CHALLENGES.iter() {
        assert!(ids.contains(challenge.after.as_str()) && challenge.ways.iter().collect::<HashSet<_>>().len() >= 2, "{}", challenge.task.goal);
    }
    for mission in missions::MISSIONS.iter() {
        assert!(ids.contains(mission.after.as_str()) && mission.ways.len() >= 2, "{}", mission.title);
        assert_eq!(mission.files.keys().collect::<HashSet<_>>(), mission.targets.keys().collect::<HashSet<_>>());
    }
    assert_eq!(evaluation::tasks("pre").len(), evaluation::tasks("post").len());
    assert!(evaluation::lesson("pre").tasks.iter().all(|t| t.solution == "—"), "no answers leak");
}

#[test]
fn quick_practice_fits_the_time() {
    assert_eq!(quick::how_many(1, None), 5);
    assert_eq!(quick::how_many(5, Some(30.0)), 10);
    assert_eq!(quick::how_many(1, Some(300.0)), 2);
    let done: HashSet<String> = LESSONS.iter().take(9).map(|l| l.id.clone()).collect();
    assert!(quick::pools(&LESSONS, &HashSet::new()).is_empty());
    let pools = quick::pools(&LESSONS, &done);
    assert!(!pools.contains_key("macros"));
    let picked = quick::tasks(&pools["repeats"], 12, "s");
    assert_eq!(picked.len(), 12);
    assert_eq!(picked.iter().map(|t| t.index).collect::<HashSet<_>>().len(), pools["repeats"].len());
}
