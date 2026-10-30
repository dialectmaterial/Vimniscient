//! Progress, kept in ~/.local/share/vimniscient/progress.db.

use super::cards::{Card, DECK_ORDER, Deck, home};
use super::drills::Drill;
use super::lessons::{Lesson, Task};
use super::results::TaskResult;
use super::srs::{self, Item};
use chrono::{Days, Local, NaiveDate};
use indexmap::IndexMap;
use rusqlite::{Connection, OptionalExtension, params};
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

const HARDTIME_MIN_DAYS: u64 = 28;
const HARDTIME_AFTER: &str = "w2d7-review";
const NEW_CARDS_PER_DAY: i64 = 10;
const VIM_FIRST_WEEKS: u32 = 2; // new cards are Vim ones first until the lessons pass this week
const NEW_DRILLS_PER_DAY: usize = 2;

const SCHEMA: &str = "
CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, lesson TEXT NOT NULL, task INTEGER NOT NULL,
    status TEXT NOT NULL, count INTEGER NOT NULL, ref INTEGER NOT NULL, keys TEXT NOT NULL, hints INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, kind TEXT NOT NULL, ease REAL NOT NULL, interval REAL NOT NULL, due TEXT NOT NULL,
    reps INTEGER NOT NULL, lapses INTEGER NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS card_log (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, card TEXT NOT NULL, correct INTEGER NOT NULL, answer TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS placed (lesson TEXT PRIMARY KEY, ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drill_log (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, drill TEXT NOT NULL, seconds REAL NOT NULL, hinted INTEGER NOT NULL, skipped INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS endless_runs (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, start INTEGER NOT NULL, level INTEGER NOT NULL,
    climbed INTEGER NOT NULL, missed INTEGER NOT NULL, fixed INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS vimgolf (id TEXT PRIMARY KEY, title TEXT NOT NULL, assigned TEXT NOT NULL, best INTEGER, score INTEGER, solved TEXT);
";

pub fn today() -> NaiveDate {
    Local::now().date_naive()
}

fn now() -> String {
    Local::now().format("%Y-%m-%dT%H:%M:%S").to_string()
}

fn day(text: &str) -> NaiveDate {
    NaiveDate::parse_from_str(text, "%Y-%m-%d").unwrap_or_default()
}

/// VIMNISCIENT_DATA points somewhere else, e.g. for testing without touching real progress.
pub fn data_dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("VIMNISCIENT_DATA").filter(|d| !d.is_empty()) {
        return dir.into();
    }
    std::env::var_os("XDG_DATA_HOME").map(PathBuf::from).unwrap_or_else(|| home().join(".local/share")).join("vimniscient")
}

fn item_row(row: &rusqlite::Row) -> rusqlite::Result<Item> {
    Ok(Item {
        id: row.get(0)?,
        kind: row.get(1)?,
        ease: row.get(2)?,
        interval: row.get(3)?,
        due: Some(day(&row.get::<_, String>(4)?)),
        reps: row.get(5)?,
        lapses: row.get(6)?,
        created: Some(day(&row.get::<_, String>(7)?)),
    })
}

const ITEM_COLUMNS: &str = "SELECT id, kind, ease, interval, due, reps, lapses, created FROM items";

/// What an Endless run came to.
#[derive(Clone, Debug, Default)]
pub struct Run {
    pub start: usize,
    pub level: usize,
    pub climbed: usize,
    pub missed: usize,
    pub fixed: usize,
}

pub struct Progress {
    pub db: Connection,
}

impl Progress {
    pub fn open() -> rusqlite::Result<Progress> {
        let dir = data_dir();
        std::fs::create_dir_all(&dir).map_err(|e| rusqlite::Error::ToSqlConversionFailure(Box::new(e)))?;
        let started = dir.join("started");
        if !started.exists() {
            let _ = std::fs::write(started, format!("{}\n", today()));
        }
        let db = Connection::open(dir.join("progress.db"))?;
        db.execute_batch(SCHEMA)?;
        let progress = Progress { db };
        let columns = progress.columns("attempts")?;
        if !columns.contains("phase") {
            progress.db.execute_batch("ALTER TABLE attempts ADD COLUMN phase TEXT NOT NULL DEFAULT 'recall'")?;
        }
        for column in ["seconds", "first"] {
            if !columns.contains(column) {
                progress.db.execute_batch(&format!("ALTER TABLE attempts ADD COLUMN {column} REAL"))?;
            }
        }
        if !progress.columns("card_log")?.contains("intro") {
            progress.db.execute_batch("ALTER TABLE card_log ADD COLUMN intro INTEGER NOT NULL DEFAULT 0")?;
        }
        Ok(progress)
    }

    fn columns(&self, table: &str) -> rusqlite::Result<HashSet<String>> {
        let mut statement = self.db.prepare(&format!("PRAGMA table_info({table})"))?;
        let names = statement.query_map([], |row| row.get::<_, String>(1))?.collect();
        names
    }

    // spaced repetition items

    pub fn item(&self, id: &str) -> Option<Item> {
        self.db.query_row(&format!("{ITEM_COLUMNS} WHERE id = ?"), [id], item_row).optional().ok().flatten()
    }

    pub fn items(&self, kind: &str) -> IndexMap<String, Item> {
        let Ok(mut statement) = self.db.prepare(&format!("{ITEM_COLUMNS} WHERE kind = ?")) else { return IndexMap::new() };
        statement.query_map([kind], item_row).map(|rows| rows.flatten().map(|item| (item.id.clone(), item)).collect()).unwrap_or_default()
    }

    pub fn save(&self, item: &Item) {
        let (due, created) = (item.due.unwrap_or_default().to_string(), item.created.unwrap_or_default().to_string());
        self.run("INSERT OR REPLACE INTO items (id, kind, ease, interval, due, reps, lapses, created) VALUES (?,?,?,?,?,?,?,?)",
                 params![item.id, item.kind, item.ease, item.interval, due, item.reps, item.lapses, created]);
    }

    fn run(&self, sql: &str, values: impl rusqlite::Params) {
        if let Err(error) = self.db.execute(sql, values) {
            eprintln!("vimniscient: couldn't save progress: {error}");
        }
    }

    pub fn grade(&self, id: &str, kind: &str, grade: u8) -> Item {
        let mut item = self.item(id).unwrap_or_else(|| Item::new(id, kind));
        srs::review(&mut item, grade, today());
        self.save(&item);
        item
    }

    fn attempt(&self, ts: &str, r: &TaskResult, phase: &str) {
        self.run("INSERT INTO attempts (ts, lesson, task, status, count, ref, keys, hints, phase, seconds, first) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 params![ts, r.task.lesson_id, r.task.index, r.status, r.count, r.task.reference(), r.keys, r.hints, phase, r.seconds, r.first]);
    }

    // vim tasks

    pub fn record(&self, results: &[TaskResult]) {
        let ts = now();
        for r in results {
            if r.status == "unseen" || (r.status == "quit" && r.keys.is_empty()) {
                continue; // not tried: opening a lesson and leaving isn't an attempt
            }
            self.attempt(&ts, r, &r.task.phase);
            // Only recall says whether you know it; the Learn round shows the keys.
            if r.task.phase == "recall"
                && let Some(grade) = srs::task_grade(&r.status, r.count, r.task.reference(), r.hints)
            {
                self.grade(&r.task.item_id(), "task", grade);
            }
        }
    }

    /// Fewest keys per solved task index.
    pub fn best(&self, lesson: &Lesson) -> HashMap<usize, usize> {
        let sql = "SELECT task, MIN(count) FROM attempts WHERE lesson = ? AND status = 'solved' AND phase = 'recall' GROUP BY task";
        let Ok(mut statement) = self.db.prepare(sql) else { return HashMap::new() };
        statement.query_map([&lesson.id], |row| Ok((row.get(0)?, row.get(1)?))).map(|rows| rows.flatten().collect()).unwrap_or_default()
    }

    pub fn is_placed(&self, lesson: &Lesson) -> bool {
        self.exists("SELECT 1 FROM placed WHERE lesson = ?", [&lesson.id])
    }

    fn exists(&self, sql: &str, values: impl rusqlite::Params) -> bool {
        self.db.query_row(sql, values, |_| Ok(())).optional().ok().flatten().is_some()
    }

    pub fn is_done(&self, lesson: &Lesson) -> bool {
        self.is_placed(lesson) || self.best(lesson).len() == lesson.tasks.len()
    }

    pub fn next_lesson<'a>(&self, lessons: &'a [Lesson]) -> Option<&'a Lesson> {
        lessons.iter().find(|lesson| !self.is_done(lesson))
    }

    pub fn done(&self, lessons: &[Lesson]) -> HashSet<String> {
        lessons.iter().filter(|lesson| self.is_done(lesson)).map(|lesson| lesson.id.clone()).collect()
    }

    /// Whether a lesson ran today. Only lessons have a Learn round, so a review doesn't count.
    pub fn lesson_today(&self) -> bool {
        self.exists("SELECT 1 FROM attempts WHERE phase = 'learn' AND ts >= ? LIMIT 1", [today().to_string()])
    }

    /// Item ids of the tasks tried today, in any session.
    pub fn practised_today(&self) -> HashSet<String> {
        let Ok(mut statement) = self.db.prepare("SELECT lesson, task FROM attempts WHERE ts >= ? AND status != 'quit'") else { return HashSet::new() };
        statement.query_map([today().to_string()], |row| Ok(format!("task:{}#{}", row.get::<_, String>(0)?, row.get::<_, i64>(1)?)))
            .map(|rows| rows.flatten().collect()).unwrap_or_default()
    }

    pub fn current_week(&self, lessons: &[Lesson]) -> u32 {
        self.next_lesson(lessons).map_or_else(|| lessons.iter().map(|l| l.week).max().unwrap_or(0) + 1, |l| l.week)
    }

    /// The next version of a task to practise: each recall moves on to another text.
    pub fn version_for(&self, task: &Task) -> Task {
        let n: i64 = self.db.query_row("SELECT COUNT(*) FROM attempts WHERE lesson = ? AND task = ? AND phase = 'recall' AND status != 'quit'",
                                       params![task.lesson_id, task.index], |row| row.get(0)).unwrap_or(0);
        task.choice(n as usize + 1, &format!("{}:{n}", task.item_id()))
    }

    /// Tasks from earlier days that are due for review, most overdue first.
    pub fn due_tasks(&self, lessons: &[Lesson], limit: Option<usize>) -> Vec<Task> {
        let tasks: HashMap<String, &Task> = lessons.iter().flat_map(|l| &l.tasks).map(|t| (t.item_id(), t)).collect();
        let mut due: Vec<Item> = self.items("task").into_values().filter(|i| i.due <= Some(today()) && tasks.contains_key(&i.id)).collect();
        due.sort_by_key(|item| (item.due, -item.lapses));
        due.truncate(limit.unwrap_or(usize::MAX));
        due.iter().map(|item| self.version_for(tasks[&item.id])).collect()
    }

    pub fn mark_known(&self, known: &[Lesson], tested: &HashSet<String>) {
        for lesson in known {
            self.run("INSERT OR IGNORE INTO placed (lesson, ts) VALUES (?, ?)", params![lesson.id, now()]);
            // The tasks that weren't tested come up in review within a week.
            for t in &lesson.tasks {
                let id = t.item_id();
                if !tested.contains(&id) && self.item(&id).is_none() {
                    let mut item = Item::new(&id, "task");
                    item.interval = 7.0;
                    item.due = Some(today() + Days::new(7));
                    item.created = Some(today());
                    self.save(&item);
                }
            }
        }
    }

    /// Forget what the placement test skipped; returns how many lessons.
    pub fn reset_placement(&self) -> usize {
        self.db.execute("DELETE FROM placed", []).unwrap_or(0)
    }

    // cards

    pub fn log_card(&self, card: &Card, correct: bool, answer: &str, intro: bool) {
        self.run("INSERT INTO card_log (ts, card, correct, answer, intro) VALUES (?,?,?,?,?)", params![now(), card.id, correct, answer, intro]);
    }

    /// Whether this card was ever answered from memory (not just typed when introduced).
    pub fn ever_right(&self, id: &str) -> bool {
        self.exists("SELECT 1 FROM card_log WHERE card = ? AND correct = 1 AND intro = 0 LIMIT 1", [id])
    }

    /// Cards for lessons you've done: a card with a `day` waits for that day's lesson, one
    /// with only a `week` comes in when that week starts.
    pub fn unlocked(&self, decks: &IndexMap<String, Deck>, lessons: &[Lesson]) -> Vec<Card> {
        let reached = self.next_lesson(lessons).map_or_else(|| (lessons.iter().map(|l| l.week).max().unwrap_or(0) + 1, 0), |l| (l.week, l.day));
        decks.values().flat_map(|deck| &deck.cards)
            .filter(|c| (c.week, c.day) < reached || (c.week == reached.0 && c.day == 0)).cloned().collect()
    }

    pub fn due_cards(&self, decks: &IndexMap<String, Deck>, lessons: &[Lesson], limit: Option<usize>) -> Vec<Card> {
        let items = self.items("card");
        let mut due: Vec<Card> = self.unlocked(decks, lessons).into_iter().filter(|c| items.get(&c.id).is_some_and(|i| i.due <= Some(today()))).collect();
        due.sort_by_key(|c| items[&c.id].due);
        due.truncate(limit.unwrap_or(usize::MAX));
        due
    }

    /// Today's unseen cards, taking turns between decks.
    pub fn new_cards(&self, decks: &IndexMap<String, Deck>, lessons: &[Lesson]) -> Vec<Card> {
        let items = self.items("card");
        let mut left = NEW_CARDS_PER_DAY - items.values().filter(|i| i.created == Some(today())).count() as i64;
        let mut unseen: IndexMap<String, Vec<Card>> = IndexMap::new();
        for card in self.unlocked(decks, lessons) {
            if !items.contains_key(&card.id) {
                unseen.entry(card.deck.clone()).or_default().push(card);
            }
        }
        for cards in unseen.values_mut() {
            cards.sort_by_key(|c| c.order);
        }
        let mut picked = Vec::new();
        let mut take = |deck: &str, unseen: &mut IndexMap<String, Vec<Card>>, left: &mut i64| {
            if let Some(cards) = unseen.get_mut(deck)
                && *left > 0
                && !cards.is_empty()
            {
                picked.push(cards.remove(0));
                *left -= 1;
            }
        };
        let order: Vec<String> = DECK_ORDER.iter().map(|d| d.to_string()).filter(|d| unseen.contains_key(d))
            .chain(unseen.keys().filter(|d| !DECK_ORDER.contains(&d.as_str())).cloned()).collect();
        // In the first weeks, Vim (and your own habits) before the other decks.
        if self.current_week(lessons) <= VIM_FIRST_WEEKS {
            for deck in ["habits", "vim"] {
                while left > 0 && unseen.get(deck).is_some_and(|c| !c.is_empty()) {
                    take(deck, &mut unseen, &mut left);
                }
            }
        }
        while left > 0 && order.iter().any(|d| !unseen[d].is_empty()) {
            for deck in &order {
                take(deck, &mut unseen, &mut left);
            }
        }
        picked
    }

    // practice that isn't graded

    /// Choose, quick practice, missions, the eval: for the streak and not for grades.
    pub fn record_ungraded(&self, results: &[TaskResult], phase: &str) {
        let ts = now();
        for r in results.iter().filter(|r| r.status != "unseen" && !(r.status == "quit" && r.keys.is_empty())) {
            self.attempt(&ts, r, phase);
        }
    }

    /// When each Choose task or mission was last tried.
    pub fn last_tried(&self, phase: &str) -> HashMap<usize, String> {
        let Ok(mut statement) = self.db.prepare("SELECT task, MAX(ts) FROM attempts WHERE phase = ? GROUP BY task") else { return HashMap::new() };
        statement.query_map([phase], |row| Ok((row.get(0)?, row.get(1)?))).map(|rows| rows.flatten().collect()).unwrap_or_default()
    }

    /// Attempts go in as phase 'endless': they count for the streak, not for lessons or reviews.
    pub fn record_endless(&self, results: &[TaskResult], run: &Run) {
        let ts = now();
        let tried: Vec<&TaskResult> = results.iter().filter(|r| !(r.status == "quit" && r.keys.is_empty())).collect();
        for r in &tried {
            self.attempt(&ts, r, "endless");
        }
        if !tried.is_empty() {
            self.run("INSERT INTO endless_runs (ts, start, level, climbed, missed, fixed) VALUES (?,?,?,?,?,?)",
                     params![ts, run.start, run.level, run.climbed, run.missed, run.fixed]);
        }
    }

    pub fn endless_best(&self) -> usize {
        self.db.query_row("SELECT MAX(level) FROM endless_runs", [], |row| row.get::<_, Option<usize>>(0)).ok().flatten().unwrap_or(0)
    }

    /// Where a new run starts: a little below where the last one ended.
    pub fn endless_start(&self, below: usize) -> usize {
        self.db.query_row("SELECT level FROM endless_runs ORDER BY id DESC LIMIT 1", [], |row| row.get::<_, usize>(0))
            .map_or(1, |level| level.saturating_sub(below).max(1))
    }

    // omarchy drills

    pub fn log_drill(&self, drill: &str, seconds: f64, hinted: bool, skipped: bool) {
        self.run("INSERT INTO drill_log (ts, drill, seconds, hinted, skipped) VALUES (?,?,?,?,?)", params![now(), drill, seconds, hinted, skipped]);
    }

    pub fn due_drills(&self, drills: &[Drill]) -> Vec<Drill> {
        let items = self.items("drill");
        drills.iter().filter(|d| items.get(&d.item_id()).is_some_and(|i| i.due <= Some(today()))).cloned().collect()
    }

    pub fn new_drills(&self, drills: &[Drill]) -> Vec<Drill> {
        let items = self.items("drill");
        let left = NEW_DRILLS_PER_DAY.saturating_sub(items.values().filter(|i| i.created == Some(today())).count());
        drills.iter().filter(|d| !items.contains_key(&d.item_id())).take(left).cloned().collect()
    }

    // vimgolf

    pub fn vimgolf_assigned_today(&self) -> Option<String> {
        self.db.query_row("SELECT id FROM vimgolf WHERE assigned = ? ORDER BY rowid DESC LIMIT 1", [today().to_string()], |row| row.get(0)).optional().ok().flatten()
    }

    pub fn vimgolf_tried(&self) -> HashSet<String> {
        let Ok(mut statement) = self.db.prepare("SELECT id FROM vimgolf") else { return HashSet::new() };
        statement.query_map([], |row| row.get(0)).map(|rows| rows.flatten().collect()).unwrap_or_default()
    }

    /// Remember a challenge that doesn't fit, so it isn't fetched again tomorrow.
    pub fn vimgolf_skip(&self, id: &str, title: &str) {
        self.run("INSERT OR IGNORE INTO vimgolf (id, title, assigned) VALUES (?, ?, '')", params![id, title]);
    }

    pub fn vimgolf_assign(&self, id: &str, title: &str, best: Option<usize>) {
        self.run("INSERT INTO vimgolf (id, title, assigned, best) VALUES (?, ?, ?, ?)", params![id, title, today().to_string(), best]);
    }

    /// Store a solved run; returns the VimGolf-style score (keys + saving).
    pub fn record_vimgolf(&self, id: &str, result: &TaskResult, save_keys: usize) -> Option<usize> {
        if result.status != "solved" {
            return None;
        }
        let score = result.count + save_keys;
        self.run("UPDATE vimgolf SET score = MIN(COALESCE(score, ?1), ?1), solved = COALESCE(solved, ?2) WHERE id = ?3", params![score, now(), id]);
        Some(score)
    }

    pub fn vimgolf_done_today(&self) -> bool {
        self.exists("SELECT 1 FROM vimgolf WHERE assigned = ? AND solved IS NOT NULL", [today().to_string()])
    }

    /// (day, title, your score, best) for challenges given out, newest first.
    pub fn vimgolf_history(&self, limit: usize) -> Vec<(String, String, Option<i64>, Option<i64>)> {
        let sql = "SELECT assigned, title, score, best FROM vimgolf WHERE assigned != '' ORDER BY assigned DESC, rowid DESC LIMIT ?";
        let Ok(mut statement) = self.db.prepare(sql) else { return Vec::new() };
        statement.query_map([limit], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?))).map(|rows| rows.flatten().collect()).unwrap_or_default()
    }

    // overview

    pub fn days_trained(&self) -> HashSet<NaiveDate> {
        let sql = "SELECT DISTINCT substr(ts, 1, 10) FROM attempts UNION SELECT DISTINCT substr(ts, 1, 10) FROM card_log UNION SELECT DISTINCT substr(ts, 1, 10) FROM drill_log";
        let Ok(mut statement) = self.db.prepare(sql) else { return HashSet::new() };
        statement.query_map([], |row| row.get::<_, String>(0)).map(|rows| rows.flatten().map(|d| day(&d)).collect()).unwrap_or_default()
    }

    pub fn streak(&self) -> usize {
        let days = self.days_trained();
        let mut current = if days.contains(&today()) { today() } else { today() - Days::new(1) };
        let mut n = 0;
        while days.contains(&current) {
            n += 1;
            current = current - Days::new(1);
        }
        n
    }

    /// The median time of a timed task, once there are enough of them to go by.
    pub fn typical_task_seconds(&self) -> Option<f64> {
        let mut statement = self.db.prepare("SELECT seconds FROM attempts WHERE seconds IS NOT NULL ORDER BY id DESC LIMIT 200").ok()?;
        let mut rows: Vec<f64> = statement.query_map([], |row| row.get(0)).ok()?.flatten().collect();
        rows.sort_by(f64::total_cmp);
        (rows.len() >= 10).then(|| rows[rows.len() / 2])
    }

    /// About how long you've practised today: timed tasks as timed, the rest estimated.
    pub fn seconds_today(&self, card_seconds: f64, task_seconds: f64) -> f64 {
        let date = today().to_string();
        let (timed, untimed): (f64, f64) = self.db.query_row(
            "SELECT COALESCE(SUM(seconds), 0), COALESCE(SUM(seconds IS NULL), 0) FROM attempts WHERE ts >= ? AND status != 'quit'",
            [&date], |row| Ok((row.get(0)?, row.get(1)?))).unwrap_or((0.0, 0.0));
        let cards: f64 = self.db.query_row("SELECT COUNT(*) FROM card_log WHERE ts >= ?", [&date], |row| row.get(0)).unwrap_or(0.0);
        let drills: f64 = self.db.query_row("SELECT COALESCE(SUM(seconds), 0) FROM drill_log WHERE ts >= ?", [&date], |row| row.get(0)).unwrap_or(0.0);
        timed + untimed * task_seconds + cards * card_seconds + drills
    }

    /// Per lesson, from tasks solved from memory that were timed: how many, the median of
    /// the first `recent` and the latest `recent`, and the median before the first key lately.
    pub fn speed_by_lesson(&self, recent: usize) -> HashMap<String, (usize, f64, f64, Option<f64>)> {
        fn median(values: &[f64]) -> f64 {
            let mut sorted = values.to_vec();
            sorted.sort_by(f64::total_cmp);
            let mid = sorted.len() / 2;
            if sorted.len() % 2 == 1 { sorted[mid] } else { (sorted[mid - 1] + sorted[mid]) / 2.0 }
        }
        let sql = "SELECT lesson, seconds, first FROM attempts WHERE status = 'solved' AND phase != 'learn' AND seconds IS NOT NULL ORDER BY id";
        let mut by_lesson: IndexMap<String, Vec<(f64, Option<f64>)>> = IndexMap::new();
        if let Ok(mut statement) = self.db.prepare(sql)
            && let Ok(rows) = statement.query_map([], |row| Ok((row.get::<_, String>(0)?, row.get(1)?, row.get(2)?)))
        {
            for (lesson, seconds, first) in rows.flatten() {
                by_lesson.entry(lesson).or_default().push((seconds, first));
            }
        }
        let mut out = HashMap::new();
        for (lesson, timed) in by_lesson {
            if timed.len() < 2 {
                continue;
            }
            let latest = &timed[timed.len().saturating_sub(recent)..];
            let firsts: Vec<f64> = latest.iter().filter_map(|t| t.1).collect();
            let seconds = |part: &[(f64, Option<f64>)]| median(&part.iter().map(|t| t.0).collect::<Vec<_>>());
            out.insert(lesson, (timed.len(), seconds(&timed[..recent.min(timed.len())]), seconds(latest), (!firsts.is_empty()).then(|| median(&firsts))));
        }
        out
    }

    /// (day, solved tasks, keys typed, reference keys) for recent training days.
    pub fn efficiency_by_day(&self, limit: usize) -> Vec<(String, i64, i64, i64)> {
        let sql = "SELECT substr(ts, 1, 10) AS d, COUNT(*), SUM(count), SUM(ref) FROM attempts WHERE status = 'solved' AND phase = 'recall' GROUP BY d ORDER BY d DESC LIMIT ?";
        let Ok(mut statement) = self.db.prepare(sql) else { return Vec::new() };
        statement.query_map([limit], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?))).map(|rows| rows.flatten().collect()).unwrap_or_default()
    }

    /// (day, answered, correct) for recent card days.
    pub fn card_accuracy(&self, limit: usize) -> Vec<(String, i64, i64)> {
        let sql = "SELECT substr(ts, 1, 10) AS d, COUNT(*), SUM(correct) FROM card_log WHERE intro = 0 GROUP BY d ORDER BY d DESC LIMIT ?";
        let Ok(mut statement) = self.db.prepare(sql) else { return Vec::new() };
        statement.query_map([limit], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?))).map(|rows| rows.flatten().collect()).unwrap_or_default()
    }

    pub fn hardest(&self, limit: usize) -> Vec<Item> {
        let Ok(mut statement) = self.db.prepare(&format!("{ITEM_COLUMNS} WHERE lapses > 0 ORDER BY lapses DESC, ease ASC LIMIT ?")) else { return Vec::new() };
        statement.query_map([limit], item_row).map(|rows| rows.flatten().collect()).unwrap_or_default()
    }

    /// The first day hardtime may block, lessons allowing.
    pub fn hardtime_earliest(&self) -> NaiveDate {
        let started = std::fs::read_to_string(data_dir().join("started")).unwrap_or_default();
        day(started.trim()) + Days::new(HARDTIME_MIN_DAYS)
    }

    pub fn hardtime_blocks(&self, lessons: &[Lesson]) -> bool {
        let after = lessons.iter().find(|l| l.id == HARDTIME_AFTER);
        today() >= self.hardtime_earliest() && after.is_none_or(|l| self.is_done(l))
    }

    /// Write hardtime's phase for the Neovim config; true when it blocks.
    pub fn sync_hardtime(&self, lessons: &[Lesson]) -> bool {
        let blocks = self.hardtime_blocks(lessons);
        let phase = if blocks { "block" } else { "hint" };
        let file = data_dir().join("hardtime");
        if std::fs::read_to_string(&file).map_or(true, |text| text.trim() != phase) {
            let _ = std::fs::write(file, format!("{phase}\n"));
        }
        blocks
    }
}
