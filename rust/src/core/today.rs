//! Today's routine, without the interface: which steps are left and roughly how long
//! each takes. The routine fits a daily budget, less what you've practised today
//! already. The next lesson comes first, then due reviews, due cards, drills and new
//! cards, as far as the time goes. What doesn't fit stays due and comes tomorrow; a
//! few due reviews and cards always come along.

use super::cards::{Card, Deck};
use super::drills::{self, Drill};
use super::lessons::{Lesson, Task};
use super::progress::Progress;
use super::{habits, settings, transfer};
use indexmap::IndexMap;
use std::collections::HashSet;

pub const ROUTINE: [&str; 4] = ["cards", "drills", "review", "lesson"]; // what `t` runs, in order

// Rough times. Erring on the long side is kinder than promising five minutes and taking fifteen.
pub const CARD_SECONDS: f64 = 12.0;
const DRILL_SECONDS: f64 = 45.0;
const REVIEW_TASK_SECONDS: f64 = 45.0;
const LESSON_TASK_SECONDS: f64 = 35.0; // per round; a lesson runs every task twice (Learn, Recall)
const LESSON_READING_SECONDS: f64 = 60.0;
// Even when the lesson takes up the budget, this much review comes along.
pub const MIN_DUE_CARDS: usize = 5;
const MIN_REVIEW_TASKS: usize = 2;

#[derive(Clone, Debug)]
pub struct Step {
    pub id: String,
    pub label: String,
    pub detail: String,
    pub todo: Option<bool>, // None: optional, never "left to do" (VimGolf, Endless)
    pub minutes: u32, // about how long what's left of it takes
}

pub fn minutes(seconds: f64) -> u32 {
    if seconds == 0.0 { 0 } else { ((seconds / 60.0).ceil() as u32).max(1) }
}

pub fn plural(n: usize, word: &str) -> String {
    format!("{n} {word}{}", if n == 1 { "" } else { "s" })
}

fn todays_drills(progress: &Progress, list: &[Drill]) -> Vec<Drill> {
    if drills::socket().is_none() {
        return Vec::new();
    }
    let mut found = progress.due_drills(list);
    found.extend(progress.new_drills(list));
    found
}

/// One task from each lesson that fixes a habit hardtime keeps catching (lessons you've
/// done only), skipping tasks already practised today.
fn habit_tasks(progress: &Progress, lessons: &[Lesson], exclude: &[Task]) -> Vec<Task> {
    let mut taken: HashSet<String> = exclude.iter().map(Task::item_id).chain(progress.practised_today()).collect();
    let items = progress.items("task");
    let mut tasks = Vec::new();
    for id in habits::drill_lessons(7) {
        let Some(lesson) = lessons.iter().find(|l| l.id == id && progress.is_done(l)) else { continue };
        // the task that has gone worst so far
        let ease = |t: &&Task| items.get(&t.item_id()).map_or(0.0, |item| item.ease);
        let worst = lesson.tasks.iter().filter(|t| !taken.contains(&t.item_id())).min_by(|a, b| ease(a).total_cmp(&ease(b)));
        if let Some(worst) = worst {
            tasks.push(progress.version_for(worst));
            taken.insert(worst.item_id());
        }
    }
    tasks.truncate(3);
    tasks
}

fn review_tasks(progress: &Progress, lessons: &[Lesson]) -> Vec<Task> {
    let due = progress.due_tasks(lessons, None);
    let extra = habit_tasks(progress, lessons, &due);
    due.into_iter().chain(extra).collect()
}

#[derive(Clone, Debug, Default)]
pub struct Seconds {
    pub cards: f64,
    pub drills: f64,
    pub review: f64,
    pub lesson: f64,
}

/// What today's routine holds, after the budget.
#[derive(Clone, Debug, Default)]
pub struct Work {
    pub cards: Vec<Card>,
    pub drills: Vec<Drill>,
    pub review: Vec<Task>,
    pub lesson: Option<Lesson>,
    pub due_cards: usize,
    pub due_review: usize,
    pub due_drills: usize,
    pub new_cards: usize, // of `cards`, the new ones
    pub seconds: Seconds, // about how long each step takes
    pub budget: f64, // seconds left of today's budget, before this work
}

pub fn todays_work(progress: &Progress, lessons: &[Lesson], decks: &IndexMap<String, Deck>, drill_list: &[Drill], budget_minutes: Option<u32>) -> Work {
    let task_seconds = progress.typical_task_seconds();
    let lesson_task = task_seconds.unwrap_or(LESSON_TASK_SECONDS);
    let review_task = task_seconds.map_or(REVIEW_TASK_SECONDS, |s| s * 1.3); // no keys shown, so slower
    let budget = (f64::from(budget_minutes.unwrap_or_else(settings::minutes)) * 60.0 - progress.seconds_today(CARD_SECONDS, lesson_task)).max(0.0);

    let due_cards = progress.due_cards(decks, lessons, None);
    let new_cards = progress.new_cards(decks, lessons);
    let review = review_tasks(progress, lessons);
    let todays = todays_drills(progress, drill_list);
    let lesson = progress.next_lesson(lessons).filter(|_| !progress.lesson_today()); // one a day, budget or not
    let lesson_seconds = lesson.map_or(0.0, |l| l.tasks.len() as f64 * 2.0 * lesson_task + LESSON_READING_SECONDS);

    let mut left = budget - lesson_seconds;
    let (mut take_review, mut take_due, mut take_drills, mut take_new) = (0, 0, 0, 0);
    if budget > 0.0 {
        // a little review always, then whatever fits
        take_review = MIN_REVIEW_TASKS.min(review.len());
        take_due = MIN_DUE_CARDS.min(due_cards.len());
        left -= take_review as f64 * review_task + take_due as f64 * CARD_SECONDS;
        for (taken, total, cost) in [
            (&mut take_review, review.len(), review_task),
            (&mut take_due, due_cards.len(), CARD_SECONDS),
            (&mut take_drills, todays.len(), DRILL_SECONDS),
            (&mut take_new, new_cards.len(), CARD_SECONDS),
        ] {
            let fits = (left / cost).floor().max(0.0) as usize;
            let extra = fits.min(total - *taken);
            *taken += extra;
            left -= extra as f64 * cost;
        }
    }
    let cards: Vec<Card> = due_cards.iter().take(take_due).chain(new_cards.iter().take(take_new)).cloned().collect();
    Work {
        seconds: Seconds { cards: cards.len() as f64 * CARD_SECONDS, drills: take_drills as f64 * DRILL_SECONDS, review: take_review as f64 * review_task, lesson: lesson_seconds },
        cards,
        drills: todays.iter().take(take_drills).cloned().collect(),
        review: review.iter().take(take_review).cloned().collect(),
        lesson: lesson.cloned(),
        due_cards: due_cards.len(),
        due_review: review.len(),
        due_drills: todays.len(),
        new_cards: take_new,
        budget,
    }
}

/// The routine steps still to do today.
pub fn left(steps: &[Step]) -> Vec<&Step> {
    steps.iter().filter(|s| s.todo == Some(true)).collect()
}

/// The Today pane's footer.
pub fn left_text(steps: &[Step], budget: u32) -> String {
    let over: u32 = left(steps).iter().map(|s| s.minutes).sum();
    if over == 0 {
        "all done".into()
    } else if over <= budget {
        format!("about {over} of {budget} min left")
    } else {
        format!("about {over} min left")
    }
}

/// Today's steps in order, then the extras.
pub fn plan(progress: &Progress, lessons: &[Lesson], work: &Work) -> Vec<Step> {
    let step = |id: &str, label: &str, detail: String, todo: Option<bool>, minutes: u32| Step { id: id.into(), label: label.into(), detail, todo, minutes };
    let nxt = progress.next_lesson(lessons);
    let golf_done = progress.vimgolf_done_today();
    let best = progress.endless_best();
    let picks = transfer::pick(lessons, progress);
    let lesson_detail = match nxt {
        None => "all done".to_string(),
        Some(l) if progress.lesson_today() => format!("done today · next W{} D{}", l.week, l.day),
        Some(l) => format!("W{} D{} · {}", l.week, l.day, l.title),
    };
    let due_taken = work.cards.len() - work.new_cards;
    let wait = |n: usize, done: &str| if n > 0 { format!("done · {n} wait for tomorrow") } else { done.to_string() };
    let cards_detail = if work.cards.is_empty() {
        wait(work.due_cards, "done")
    } else {
        let due = if due_taken < work.due_cards { format!("{due_taken} of {} due", work.due_cards) } else { format!("{due_taken} due") };
        format!("{due} · {} new", work.new_cards)
    };
    let review_detail = if work.review.is_empty() {
        wait(work.due_review, "nothing due")
    } else if work.review.len() < work.due_review {
        format!("{} of {} tasks", work.review.len(), work.due_review)
    } else {
        plural(work.review.len(), "task")
    };
    let drills_detail = if !work.drills.is_empty() {
        plural(work.drills.len(), "drill")
    } else if work.due_drills > 0 {
        format!("{} wait for tomorrow", plural(work.due_drills, "drill"))
    } else {
        "done".into()
    };
    vec![
        step("cards", "Cards", cards_detail, Some(!work.cards.is_empty()), minutes(work.seconds.cards)),
        step("drills", "Drills", drills_detail, Some(!work.drills.is_empty()), minutes(work.seconds.drills)),
        step("review", "Review", review_detail, Some(!work.review.is_empty()), minutes(work.seconds.review)),
        step("lesson", "Lesson", lesson_detail, Some(work.lesson.is_some()), minutes(work.seconds.lesson)),
        step("vimgolf", "VimGolf", if golf_done { "done".into() } else { "optional · today's challenge".into() }, golf_done.then_some(false), 0),
        step("quick", "Quick", "optional · 1, 2 or 5 minutes".into(), None, 0),
        step("transfer", "Choose", if picks.is_empty() { "opens after Week 1 · Day 2".into() } else { format!("optional · {} tasks, your keys", picks.len()) }, None, 0),
        step("endless", "Endless", if best > 0 { format!("best level {best}") } else { "as long as you like".into() }, None, 0),
    ]
}
