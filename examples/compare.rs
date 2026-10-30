//! Prints what the app works out from a database, as JSON, to compare with Python.

use serde_json::json;
use vimniscient::core::progress::Progress;
use vimniscient::core::{cards, drills, lessons::LESSONS, today};

fn main() {
    let p = Progress::open().unwrap();
    let lessons = &*LESSONS;
    let decks = cards::load_decks();
    let list = drills::load_drills();
    let work = today::todays_work(&p, lessons, &decks, &list, Some(15));
    let steps: Vec<_> = today::plan(&p, lessons, &work).iter().map(|s| json!([s.id, s.detail, s.todo, s.minutes])).collect();
    let mut speed: Vec<_> = p.speed_by_lesson(3).into_iter().map(|(k, v)| json!([k, v.0, round(v.1), round(v.2), v.3.map(round)])).collect();
    speed.sort_by_key(|v| v[0].to_string());
    let done: Vec<&str> = lessons.iter().filter(|l| p.is_done(l)).map(|l| l.id.as_str()).collect();
    println!("{}", serde_json::to_string_pretty(&json!({
        "streak": p.streak(), "done": done, "next": p.next_lesson(lessons).map(|l| &l.id), "typical": p.typical_task_seconds().map(round),
        "endless_best": p.endless_best(), "endless_start": p.endless_start(10), "efficiency": p.efficiency_by_day(14), "accuracy": p.card_accuracy(7),
        "hardest": p.hardest(6).iter().map(|i| i.id.clone()).collect::<Vec<_>>(), "speed": speed, "steps": steps,
        "cards": work.cards.iter().map(|c| c.id.clone()).collect::<Vec<_>>(), "new": work.new_cards, "budget": round(work.budget),
        "review": work.review.iter().map(|t| t.item_id()).collect::<Vec<_>>(), "decks": decks.iter().map(|(k, d)| json!([k, d.cards.len()])).collect::<Vec<_>>(),
        "hardtime": p.hardtime_blocks(lessons), "earliest": p.hardtime_earliest().to_string(),
    })).unwrap());
}

fn round(value: f64) -> f64 {
    (value * 1000.0).round() / 1000.0
}
