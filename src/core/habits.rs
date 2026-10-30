//! Bad habits, read from hardtime.nvim's log (~/.local/state/nvim/hardtime.nvim.log).
//! `Use dj instead of 2dd` becomes a card; `You pressed the j key too soon!` and
//! `The <Up> key is disabled!` bring the motion lessons back.

use super::cards::{Card, Deck, home};
use super::keys::split_keys;
use super::mnemonics::OPERATORS;
use super::progress::today;
use chrono::{Days, NaiveDate};
use fancy_regex::Regex;
use indexmap::IndexMap;
use std::sync::LazyLock;

static LINE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^\[\w+\s+\w{3} (\d{2} \w{3} \d{4}) [^\]]*\] (.+)$").expect("a valid pattern"));
static USE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^Use (.+) instead of (.+)$").expect("a valid pattern"));
static TOO_SOON: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^You pressed the (\S+) key too soon!").expect("a valid pattern"));
static DISABLED: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^The (\S+) key is disabled!").expect("a valid pattern"));

#[derive(Clone, Debug)]
pub struct Habit {
    pub message: String,
    pub total: usize,
    pub recent: usize, // in the last two weeks
    pub last: NaiveDate,
}

fn read_log() -> Vec<(NaiveDate, String)> {
    let state = std::env::var_os("XDG_STATE_HOME").map(std::path::PathBuf::from).unwrap_or_else(|| home().join(".local/state"));
    let Ok(bytes) = std::fs::read(state.join("nvim/hardtime.nvim.log")) else { return Vec::new() };
    let text = String::from_utf8_lossy(&bytes);
    let mut entries = Vec::new();
    for line in text.lines() {
        if let Ok(Some(caps)) = LINE.captures(line.trim())
            && let Ok(day) = NaiveDate::parse_from_str(&caps[1], "%d %b %Y")
        {
            entries.push((day, caps[2].trim().to_string()));
        }
    }
    entries
}

/// Every distinct message, most frequent recently first.
pub fn habits(days: u64) -> Vec<Habit> {
    let since = today() - Days::new(days);
    let mut found: IndexMap<String, Habit> = IndexMap::new();
    for (day, message) in read_log() {
        let habit = found.entry(message.clone()).or_insert(Habit { message, total: 0, recent: 0, last: day });
        habit.total += 1;
        habit.recent += usize::from(day >= since);
        habit.last = habit.last.max(day);
    }
    let mut list: Vec<Habit> = found.into_values().collect();
    list.sort_by(|a, b| (b.recent, b.total, &a.message).cmp(&(a.recent, a.total, &b.message)));
    list
}

/// One card per "Use X instead of Y" hint, most frequent first.
pub fn habit_deck() -> Deck {
    let mut deck = Deck { id: "habits".into(), title: "Your habits".into(), cards: Vec::new() };
    for (i, habit) in habits(14).iter().enumerate() {
        let Ok(Some(caps)) = USE.captures(&habit.message) else { continue };
        let (better, worse) = (&caps[1], &caps[2]);
        let n = split_keys(better).len();
        let first = better.chars().next().map(String::from).unwrap_or_default();
        let verb = if OPERATORS.contains(&first.as_str()) { "Verb first, then the motion. " } else { "" };
        deck.cards.push(Card {
            deck: "habits".into(),
            id: format!("habits:{}", habit.message),
            prompt: format!("You typed {worse}. hardtime knows the same edit in {n} key{}: which?", if n == 1 { "" } else { "s" }),
            answers: vec![better.to_string()],
            style: "keys".into(),
            case_sensitive: true,
            note: format!("{verb}hardtime caught this {}×.", habit.total),
            order: i,
            ..Card::default()
        });
    }
    deck
}

fn drill_lessons_for(key: &str) -> &'static [&'static str] {
    match key {
        "j" | "k" => &["w1d6-counts", "w2d2-search", "w1d3-sentences"],
        "h" | "l" => &["w1d4-find", "w1d1-words"],
        _ => &[],
    }
}

/// Lessons worth repeating because of keys pressed over and over lately.
pub fn drill_lessons(days: u64) -> Vec<String> {
    let since = today() - Days::new(days);
    let mut keys: IndexMap<String, usize> = IndexMap::new();
    for (day, message) in read_log() {
        if day < since {
            continue;
        }
        let caps = TOO_SOON.captures(&message).ok().flatten().or_else(|| DISABLED.captures(&message).ok().flatten());
        if let Some(caps) = caps {
            let key = match &caps[1] {
                "<Down>" => "j",
                "<Up>" => "k",
                "<Left>" => "h",
                "<Right>" => "l",
                other => other,
            };
            if !drill_lessons_for(key).is_empty() {
                *keys.entry(key.to_string()).or_default() += 1;
            }
        }
    }
    let mut ranked: Vec<(String, usize)> = keys.into_iter().collect();
    ranked.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    let mut lessons: Vec<String> = Vec::new();
    for (key, _) in ranked {
        for lesson in drill_lessons_for(&key) {
            if !lessons.iter().any(|l| l == lesson) {
                lessons.push(lesson.to_string());
            }
        }
    }
    lessons
}
