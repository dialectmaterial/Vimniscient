//! Spaced repetition: a small SM-2 variant shared by cards and Vim tasks.

use chrono::{Days, NaiveDate};

pub const AGAIN: u8 = 1;
pub const HARD: u8 = 2;
pub const GOOD: u8 = 3;
pub const EASY: u8 = 4;

#[derive(Clone, Debug, PartialEq)]
pub struct Item {
    pub id: String,
    pub kind: String, // card | task | drill
    pub ease: f64,
    pub interval: f64, // days
    pub due: Option<NaiveDate>,
    pub reps: i64,
    pub lapses: i64,
    pub created: Option<NaiveDate>,
}

impl Item {
    pub fn new(id: &str, kind: &str) -> Item {
        Item { id: id.into(), kind: kind.into(), ease: 2.5, interval: 0.0, due: None, reps: 0, lapses: 0, created: None }
    }
}

/// Python's `round`: halves go to the even neighbour.
pub fn round_half_even(value: f64) -> i64 {
    let floor = value.floor();
    let rest = value - floor;
    let down = floor as i64;
    if rest > 0.5 || (rest == 0.5 && down % 2 != 0) { down + 1 } else { down }
}

/// Schedule the next review after answering with `grade`.
pub fn review(item: &mut Item, grade: u8, today: NaiveDate) {
    match grade {
        AGAIN => {
            item.lapses += 1;
            item.reps = 0;
            item.interval = 1.0;
            item.ease = (item.ease - 0.2).max(1.3);
        }
        HARD => {
            item.reps += 1;
            item.interval = (item.interval * 1.2).max(1.0);
            item.ease = (item.ease - 0.15).max(1.3);
        }
        GOOD => {
            item.interval = match item.reps {
                0 => 1.0,
                1 => 3.0,
                _ => item.interval * item.ease,
            };
            item.reps += 1;
        }
        _ => {
            // EASY: known already, or done without effort
            item.interval = if item.reps == 0 { 4.0 } else { item.interval * item.ease * 1.3 };
            item.reps += 1;
            item.ease += 0.15;
        }
    }
    item.created = item.created.or(Some(today));
    item.due = Some(today + Days::new(round_half_even(item.interval).max(1) as u64));
}

/// How well a Vim task went; None when it says nothing (not reached, or quit midway).
pub fn task_grade(status: &str, count: usize, reference: usize, hints: usize) -> Option<u8> {
    if matches!(status, "unseen" | "quit") {
        return None;
    }
    if status != "solved" {
        return Some(AGAIN);
    }
    if hints > 0 {
        return Some(HARD);
    }
    if count <= reference {
        return Some(EASY);
    }
    Some(if count as f64 <= reference as f64 * 1.5 + 1.0 { GOOD } else { HARD })
}
