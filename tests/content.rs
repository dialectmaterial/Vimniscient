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

/// Your review history is kept per `task:<lesson>#<position>`. Moving a task within its
/// lesson would hand its history to whichever task lands on that position, so every id
/// stays tied to the goal it was recorded with. New tasks go at the end; `UPDATE_GOLDEN=1`
/// records them, but never rewrites an id already there: rewording a goal on purpose is a
/// hand edit of tests/golden/task_ids.json.
#[test]
fn task_ids_keep_their_tasks() {
    let path = format!("{}/tests/golden/task_ids.json", env!("CARGO_MANIFEST_DIR"));
    let mut recorded: serde_json::Map<String, serde_json::Value> =
        std::fs::read_to_string(&path).ok().and_then(|text| serde_json::from_str(&text).ok()).unwrap_or_default();
    let mut added = false;
    for task in LESSONS.iter().flat_map(|l| &l.tasks) {
        match recorded.get(&task.item_id()) {
            Some(goal) => assert_eq!(goal, task.goal.as_str(), "{} is a different task now: did tasks move?", task.item_id()),
            None => {
                assert!(std::env::var_os("UPDATE_GOLDEN").is_some(), "{} is new: UPDATE_GOLDEN=1 cargo test records it", task.item_id());
                recorded.insert(task.item_id(), task.goal.clone().into());
                added = true;
            }
        }
    }
    if added {
        std::fs::write(&path, format!("{}\n", serde_json::to_string_pretty(&recorded).unwrap())).unwrap();
    }
}

#[test]
fn recall_in_weeks_one_and_two_is_always_a_new_text() {
    use vimniscient::core::lessons::two_rounds;
    for lesson in LESSONS.iter().filter(|l| l.week <= 2) {
        for task in &lesson.tasks {
            assert!(!task.generator.is_empty(), "{} has no generator", task.item_id());
            let written: Vec<&Vec<String>> = task.siblings.iter().map(|t| &t.start).collect();
            let texts: Vec<Vec<String>> = (0..task.choices() * 2).map(|n| task.choice(n, &format!("day{n}")).start).collect();
            assert!(texts.iter().all(|t| !written.contains(&t)), "{} recalls a written text", task.item_id());
            assert_eq!(texts.iter().collect::<HashSet<_>>().len(), texts.len(), "{} repeats a text", task.item_id());
        }
        for day in ["2026-11-03", "2026-11-04"] {
            for t in two_rounds(lesson, day) {
                let written = t.siblings.iter().any(|v| v.start == t.start);
                assert_eq!(written, t.phase == "learn", "{} {} on {day}", t.item_id(), t.phase);
            }
        }
    }
}

#[test]
fn the_corpus_is_plain_words_that_fit() {
    use vimniscient::core::corpus::PROSE;
    assert!(PROSE.len() > 5000);
    for line in PROSE.iter() {
        let words: Vec<&str> = line.trim_end_matches('.').split([' ', ',']).filter(|w| !w.is_empty()).collect();
        assert!((14..=70).contains(&line.len()) && line.ends_with('.'), "{line}");
        assert!(line.starts_with(|c: char| c.is_ascii_uppercase()), "{line}");
        assert!(words.iter().all(|w| w.chars().all(|c| c.is_ascii_alphabetic())), "{line}");
        assert!(!line.contains("  ") && !line.contains(" ,"), "{line}");
    }
}

#[test]
fn generated_texts_fit_the_box_and_need_work() {
    let parent = &LESSONS[0].tasks[0];
    for kind in generate::KINDS {
        for n in 0..100 {
            let t = generate::generate(kind, &n.to_string(), parent);
            assert!(t.start.iter().chain(&t.target).all(|l| l.len() <= 70), "{kind} seed {n} is too wide");
            assert_ne!(t.start, t.target, "{kind} seed {n} starts solved");
            assert!(t.cursor.0 >= 1 && t.cursor.0 <= t.start.len() && t.cursor.1 <= t.start[t.cursor.0 - 1].len(), "{kind} seed {n}: cursor off the text");
        }
    }
}
