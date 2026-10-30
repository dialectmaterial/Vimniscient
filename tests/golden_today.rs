//! Today's plan, placement and a card run against what's recorded in tests/golden/, plus
//! every generator kind producing tasks. In one test: they share a throwaway data folder.
//! Changing lessons or cards changes these on purpose: `UPDATE_GOLDEN=1 cargo test` rewrites them.

use chrono::Days;
use serde_json::{Value, json};
use vimniscient::core::card_session::CardSession;
use vimniscient::core::progress::{Progress, today};
use vimniscient::core::{cards, generate, lessons::LESSONS, placement, results::TaskResult, srs::Item, today as plan};

fn check(name: &str, got: Value) {
    let path = format!("{}/tests/golden/{name}", env!("CARGO_MANIFEST_DIR"));
    if std::env::var_os("UPDATE_GOLDEN").is_some() {
        std::fs::write(&path, format!("{}\n", serde_json::to_string_pretty(&got).unwrap())).unwrap();
        return;
    }
    let wanted: Value = serde_json::from_str(&std::fs::read_to_string(&path).expect("a golden file")).expect("JSON");
    assert_eq!(got, wanted, "{name}");
}

#[test]
fn the_day_stays_the_same() {
    let dir = std::env::temp_dir().join(format!("vimniscient-test-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    // SAFETY: this binary has only this test, and it sets these before any thread reads them.
    unsafe {
        std::env::set_var("VIMNISCIENT_DATA", dir.join("data"));
        std::env::set_var("XDG_CONFIG_HOME", dir.join("config"));
        std::env::set_var("XDG_STATE_HOME", dir.join("state"));
    }
    let progress = Progress::open().unwrap();
    let decks = cards::load_static_decks();
    let lessons = &*LESSONS;
    for lesson in &lessons[..3] {
        progress.db.execute("INSERT INTO placed (lesson, ts) VALUES (?, ?)", [lesson.id.as_str(), "2026-10-01"]).unwrap();
    }
    let unlocked = progress.unlocked(&decks, lessons);
    for (i, card) in unlocked[..40].iter().enumerate() {
        let mut item = Item::new(&card.id, "card");
        item.interval = 1.0;
        item.reps = 1;
        item.due = Some(today() - Days::new(1 + (i as u64 % 3)));
        item.created = Some(today() - Days::new(5));
        progress.save(&item);
    }
    let mut plans = serde_json::Map::new();
    for minutes in [1, 15, 120] {
        let work = plan::todays_work(&progress, lessons, &decks, &[], Some(minutes));
        let steps: Vec<Value> = plan::plan(&progress, lessons, &work).iter().map(|s| json!({"id": s.id, "detail": s.detail, "todo": s.todo, "minutes": s.minutes})).collect();
        plans.insert(minutes.to_string(), json!({
            "steps": steps,
            "cards": work.cards.iter().map(|c| &c.id).collect::<Vec<_>>(),
            "new_cards": work.new_cards,
            "lesson": work.lesson.as_ref().map(|l| &l.id),
            "review": work.review.iter().map(|t| t.item_id()).collect::<Vec<_>>(),
            "budget": work.budget,
            "seconds": {"cards": work.seconds.cards, "lesson": work.seconds.lesson},
        }));
    }
    let mut session = CardSession::new(vec![unlocked[40].clone(), unlocked[41].clone(), unlocked[0].clone()]);
    let mut trail = Vec::new();
    while let Some(card) = session.begin(&progress) {
        let typed = if trail.len() == 2 { "wrong".to_string() } else { card.answers[0].clone() };
        let taken = session.submit(&typed);
        trail.push(json!({"card": card.id, "intro": session.intro, "typed": typed, "taken": taken}));
        session.settle(&progress);
    }
    check("today.json", json!({"plans": plans, "card_run": trail, "card_score": [session.correct, session.answered]}));

    let by_id = |id: &str| lessons.iter().find(|l| l.id == id).unwrap();
    let profiles: [(&str, fn(&str, u32) -> bool); 4] = [
        ("expert", |_, _| true),
        ("beginner", |_, _| false),
        ("macros", |skill, _| skill == "macros"),
        ("ex-week-3", |skill, week| skill == "ex" && week == 3),
    ];
    let mut found = serde_json::Map::new();
    for (name, knows) in profiles {
        let mut search = placement::Search::new(lessons, Some(true));
        let mut rounds = Vec::new();
        while !search.finished() {
            let tasks = search.round();
            rounds.push(tasks.iter().map(|t| t.item_id()).collect::<Vec<_>>());
            let results: Vec<TaskResult> = tasks.iter().map(|t| {
                let lesson = by_id(&t.lesson_id);
                TaskResult::new(t, if knows(&lesson.skill, lesson.week) { "solved" } else { "skipped" }, &t.solution, t.reference(), 0)
            }).collect();
            search.update(&results);
        }
        let known: Vec<String> = search.known().iter().map(|l| l.id.clone()).collect();
        found.insert(name.to_string(), json!({"rounds": rounds, "known": known}));
    }
    check("placement.json", Value::Object(found));

    let parent = &lessons[0].tasks[0];
    for kind in generate::KINDS {
        for n in 0..200 {
            let task = generate::generate(kind, &n.to_string(), parent);
            assert_ne!(task.start, task.target, "{kind} seed {n} starts solved");
            assert_eq!(task.goal, generate::generate(kind, &n.to_string(), parent).goal, "{kind} isn't repeatable");
        }
    }
    let _ = std::fs::remove_dir_all(&dir);
}
