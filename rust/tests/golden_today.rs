//! Today's plan, placement and a card run against the Python app's, plus every generator
//! kind producing tasks. In one test: they share a throwaway data folder.

use chrono::Days;
use serde_json::{Value, json};
use vimniscient::core::card_session::CardSession;
use vimniscient::core::progress::{Progress, today};
use vimniscient::core::{cards, generate, lessons::LESSONS, placement, results::TaskResult, srs::Item, today as plan};

fn golden(name: &str) -> Value {
    let path = format!("{}/../tests/golden/{name}", env!("CARGO_MANIFEST_DIR"));
    serde_json::from_str(&std::fs::read_to_string(path).expect("run tests/make_golden.py")).expect("JSON")
}

#[test]
fn the_day_matches_python() {
    let dir = std::env::temp_dir().join(format!("vimniscient-test-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    // SAFETY: this binary has only this test, and it sets these before any thread reads them.
    unsafe {
        std::env::set_var("VIMNISCIENT_DATA", dir.join("data"));
        std::env::set_var("XDG_CONFIG_HOME", dir.join("config"));
        std::env::set_var("XDG_STATE_HOME", dir.join("state"));
    }
    let wanted = golden("today.json");
    let progress = Progress::open().unwrap();
    let decks = cards::load_static_decks();
    let lessons = &*LESSONS;
    for lesson in wanted["placed"].as_array().unwrap() {
        progress.db.execute("INSERT INTO placed (lesson, ts) VALUES (?, ?)", [lesson.as_str().unwrap(), "2026-10-01"]).unwrap();
    }
    for row in wanted["items"].as_array().unwrap() {
        let mut item = Item::new(row["id"].as_str().unwrap(), "card");
        item.interval = 1.0;
        item.reps = 1;
        item.due = Some(today() - Days::new((-row["due_days"].as_i64().unwrap()) as u64));
        item.created = Some(today() - Days::new(5));
        progress.save(&item);
    }
    for (minutes, want) in wanted["plans"].as_object().unwrap() {
        let work = plan::todays_work(&progress, lessons, &decks, &[], Some(minutes.parse().unwrap()));
        let steps: Vec<Value> = plan::plan(&progress, lessons, &work).iter().map(|s| json!({"id": s.id, "detail": s.detail, "todo": s.todo, "minutes": s.minutes})).collect();
        assert_eq!(json!(steps), want["steps"], "steps at {minutes} minutes");
        let ids: Vec<&String> = work.cards.iter().map(|c| &c.id).collect();
        assert_eq!(json!(ids), want["cards"], "cards at {minutes} minutes");
        assert_eq!(work.new_cards as u64, want["new_cards"].as_u64().unwrap());
        assert_eq!(json!(work.lesson.as_ref().map(|l| &l.id)), want["lesson"]);
        let review: Vec<String> = work.review.iter().map(|t| t.item_id()).collect();
        assert_eq!(json!(review), want["review"]);
        assert_eq!(work.budget, want["budget"].as_f64().unwrap());
        assert_eq!(work.seconds.cards, want["seconds"]["cards"].as_f64().unwrap());
        assert_eq!(work.seconds.lesson, want["seconds"]["lesson"].as_f64().unwrap());
    }

    let unlocked = progress.unlocked(&decks, lessons);
    let mut session = CardSession::new(vec![unlocked[40].clone(), unlocked[41].clone(), unlocked[0].clone()]);
    let mut trail = Vec::new();
    while let Some(card) = session.begin(&progress) {
        let typed = if trail.len() == 2 { "wrong".to_string() } else { card.answers[0].clone() };
        let taken = session.submit(&typed);
        trail.push(json!({"card": card.id, "intro": session.intro, "typed": typed, "taken": taken}));
        session.settle(&progress);
    }
    assert_eq!(json!(trail), wanted["card_run"]);
    assert_eq!(json!([session.correct, session.answered]), wanted["card_score"]);

    let by_id = |id: &str| lessons.iter().find(|l| l.id == id).unwrap();
    let wanted = golden("placement.json");
    let profiles: [(&str, fn(&str, u32) -> bool); 4] = [
        ("expert", |_, _| true),
        ("beginner", |_, _| false),
        ("macros", |skill, _| skill == "macros"),
        ("ex-week-3", |skill, week| skill == "ex" && week == 3),
    ];
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
        assert_eq!(json!({"rounds": rounds, "known": known}), wanted[name], "{name}");
    }

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
