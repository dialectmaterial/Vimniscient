//! Lessons and their tasks, from the YAML files. A task's `start` text marks the
//! cursor with ▮; every task can list `variants`, the same skill on other texts.

use super::{content, generate, keys::count_keys};
use serde_norway::Value;
use std::sync::{Arc, LazyLock};

const CURSOR: char = '▮';
const SPACE: char = '␣';
pub const SKILLS: [&str; 10] = ["text-objects", "motions", "edits", "repeats", "search", "visual", "macros", "registers", "ex", "mixed"];

#[derive(Clone, Debug, Default)]
pub struct Task {
    pub goal: String,
    pub start: Vec<String>,
    pub cursor: (usize, usize), // (1-based line, 0-based byte column), as nvim wants
    pub target: Vec<String>,
    pub solution: String,
    pub hint: String,
    pub ft: String,
    pub lesson_id: String,
    pub index: usize, // position in its lesson
    pub ref_override: Option<usize>, // when there's no reference solution (VimGolf)
    pub phase: String, // learn (keys shown) | recall (from memory) | climb (endless mode)
    pub generator: String, // a kind in generate.rs that makes new texts for this skill
    pub generated: String, // the seed, on a task made by the generator
    pub siblings: Arc<Vec<Task>>, // every version of the task, this one included
}

impl Task {
    pub fn item_id(&self) -> String {
        format!("task:{}#{}", self.lesson_id, self.index)
    }

    pub fn versions(&self) -> usize {
        self.siblings.len().max(1)
    }

    /// Version n of this task, cycling through the original and its variants.
    pub fn version(&self, n: usize) -> Task {
        if self.siblings.is_empty() {
            return self.clone();
        }
        let mut found = self.siblings[n % self.siblings.len()].clone();
        found.siblings = self.siblings.clone();
        found
    }

    /// The version after this one, for another go on a text not just seen.
    pub fn next_version(&self) -> Task {
        if !self.generated.is_empty() {
            return self.generate(&format!("{}+", self.generated)); // a generated text: another one
        }
        if self.siblings.len() < 2 {
            return self.clone();
        }
        let i = self.siblings.iter().position(|t| t.start == self.start && t.target == self.target).unwrap_or(0);
        self.version(i + 1)
    }

    /// The texts a recall can pick from: the versions, plus a generated one if it has a generator.
    pub fn choices(&self) -> usize {
        self.versions() + usize::from(!self.generator.is_empty())
    }

    /// Text n of the choices; the last is generated from `seed` when there's a generator.
    pub fn choice(&self, n: usize, seed: &str) -> Task {
        let n = n % self.choices();
        if n == self.versions() { self.generate(seed) } else { self.version(n) }
    }

    pub fn generate(&self, seed: &str) -> Task {
        generate::generate(&self.generator, seed, &self.version(0))
    }

    pub fn generate_kind(&self, kind: &str, seed: &str) -> Task {
        generate::generate(kind, seed, self)
    }

    pub fn reference(&self) -> usize {
        self.ref_override.unwrap_or_else(|| count_keys(&self.solution))
    }

    pub fn as_phase(&self, phase: &str) -> Task {
        Task { phase: phase.into(), ..self.clone() }
    }
}

#[derive(Clone, Debug, Default)]
pub struct Lesson {
    pub id: String,
    pub week: u32,
    pub day: u32,
    pub title: String,
    pub intro: String,
    pub keys: Vec<String>,
    pub tasks: Vec<Task>,
    pub review: bool, // a mixed review day (skipped by the placement test)
    pub lazyvim: bool, // needs LazyVim's text objects/plugins
    pub skill: String, // one of SKILLS: what placement and skill drills go by
}

impl Lesson {
    pub fn label(&self) -> String {
        format!("Week {} · Day {}", self.week, self.day)
    }
}

/// The text's lines with the ▮ taken out, and where it was.
pub fn parse_start(text: &str) -> (Vec<String>, (usize, usize)) {
    let mut lines: Vec<String> = text.replace(SPACE, " ").split('\n').map(str::to_string).collect();
    let marked: Vec<usize> = (0..lines.len()).filter(|&i| lines[i].contains(CURSOR)).collect();
    assert!(marked.len() == 1 && lines[marked[0]].matches(CURSOR).count() == 1, "start text needs exactly one {CURSOR}: {text:?}");
    let row = marked[0];
    let col = lines[row].find(CURSOR).expect("marked");
    lines[row] = lines[row].replace(CURSOR, "");
    (lines, (row + 1, col))
}

fn field(t: &Value, name: &str) -> Option<String> {
    t.get(name).map(content::scalar).filter(|s| !s.is_empty())
}

fn task(t: &Value, parent: Option<&Task>, lesson_id: &str, index: usize, ft: &str) -> Task {
    let (start, cursor) = parse_start(&field(t, "start").expect("a start text"));
    let inherit = |name: &str, from: fn(&Task) -> &String| field(t, name).or_else(|| parent.map(|p| from(p).clone())).unwrap_or_default();
    Task {
        goal: inherit("goal", |p| &p.goal),
        start,
        cursor,
        target: field(t, "target").unwrap_or_default().replace(SPACE, " ").split('\n').map(str::to_string).collect(),
        solution: inherit("solution", |p| &p.solution),
        hint: inherit("hint", |p| &p.hint),
        ft: t.get("ft").map(content::scalar).or_else(|| parent.map(|p| p.ft.clone())).unwrap_or_else(|| ft.to_string()),
        lesson_id: lesson_id.into(),
        index,
        phase: "recall".into(),
        generator: t.get("generate").map(content::scalar).or_else(|| parent.map(|p| p.generator.clone())).unwrap_or_default(),
        ..Task::default()
    }
}

fn load(source: &str, name: &str) -> Lesson {
    let data: Value = serde_norway::from_str(source).unwrap_or_else(|e| panic!("{name}: {e}"));
    let id = name.trim_end_matches(".yaml").to_string();
    let ft = field(&data, "ft").unwrap_or_default();
    let mut tasks = Vec::new();
    for (i, t) in data["tasks"].as_sequence().expect("tasks").iter().enumerate() {
        let first = task(t, None, &id, i, &ft);
        let mut family = vec![first.clone()];
        if let Some(variants) = t.get("variants").and_then(Value::as_sequence) {
            family.extend(variants.iter().map(|v| task(v, Some(&first), &id, i, &first.ft)));
        }
        let siblings = Arc::new(family);
        tasks.push(Task { siblings, ..first });
    }
    Lesson {
        week: data["week"].as_u64().expect("week") as u32,
        day: data["day"].as_u64().expect("day") as u32,
        title: content::scalar(&data["title"]),
        intro: field(&data, "intro").unwrap_or_default().trim().to_string(),
        keys: data.get("keys").and_then(Value::as_sequence).map(|k| k.iter().map(content::scalar).collect()).unwrap_or_default(),
        tasks,
        review: data.get("review").and_then(Value::as_bool).unwrap_or(false),
        lazyvim: data.get("lazyvim").and_then(Value::as_bool).unwrap_or(false),
        skill: content::scalar(&data["skill"]),
        id,
    }
}

/// Learn (keys shown), then Recall (the same skills on other texts, shuffled, keys
/// hidden). Which texts, and the order, change from day to day.
pub fn two_rounds(lesson: &Lesson, day: &str) -> Vec<Task> {
    let mut rng = generate::Rng::new(&format!("{}:{day}", lesson.id));
    let (mut learn, mut recall) = (Vec::new(), Vec::new());
    for t in &lesson.tasks {
        let first = rng.below(t.versions()); // Learn keeps to the written texts
        let others: Vec<usize> = (0..t.choices()).filter(|&n| n != first).collect();
        let second = if others.is_empty() { first } else { *rng.choice(&others) };
        learn.push(t.version(first).as_phase("learn"));
        recall.push(t.choice(second, &format!("{}:{day}", t.item_id())).as_phase("recall"));
    }
    rng.shuffle(&mut recall);
    learn.extend(recall);
    learn
}

pub static LESSONS: LazyLock<Vec<Lesson>> = LazyLock::new(|| {
    let mut lessons: Vec<Lesson> = content::names("lessons")
        .iter()
        .filter(|name| name.ends_with(".yaml"))
        .map(|name| load(&content::text(name), name.trim_start_matches("lessons/")))
        .collect();
    lessons.sort_by_key(|lesson| (lesson.week, lesson.day));
    lessons
});
