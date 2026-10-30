//! The placement test, by skill: a binary search along each skill's lessons. Each round
//! tests the middle of what's still open: a pass moves further along, a miss looks
//! earlier. Skills never touch each other's result. Reviews and week 6 aren't tested; a
//! review counts as known once its week's other lessons all are.

use super::cards::has_lazyvim;
use super::lessons::{Lesson, Task};
use super::{results::TaskResult, srs};
use indexmap::IndexMap;
use std::collections::{BTreeSet, HashMap, HashSet};

pub const NEXT_ROUND: &str = "That round is done. The next one follows from how it went.";

pub fn note(known: &[Lesson]) -> String {
    if known.is_empty() {
        return "No lessons skipped. Start from Week 1 · Day 1.".into();
    }
    let names: Vec<String> = known.iter().map(|l| format!("{} ({})", l.label(), l.title)).collect();
    format!("Known already: {}", names.join(", "))
}

pub struct Search<'a> {
    lessons: &'a [Lesson],
    pub seen: HashSet<String>,
    skills: IndexMap<String, Vec<&'a Lesson>>,
    low: HashMap<String, usize>, // lessons before this are known
    high: HashMap<String, usize>, // from here on, not
}

impl<'a> Search<'a> {
    pub fn new(lessons: &'a [Lesson], lazyvim: Option<bool>) -> Search<'a> {
        let lazyvim = lazyvim.unwrap_or_else(has_lazyvim);
        let mut skills: IndexMap<String, Vec<&Lesson>> = IndexMap::new();
        for lesson in lessons.iter().filter(|l| l.skill != "mixed" && (lazyvim || !l.lazyvim)) {
            skills.entry(lesson.skill.clone()).or_default().push(lesson);
        }
        let low = skills.keys().map(|s| (s.clone(), 0)).collect();
        let high = skills.iter().map(|(s, found)| (s.clone(), found.len())).collect();
        Search { lessons, seen: HashSet::new(), skills, low, high }
    }

    pub fn finished(&self) -> bool {
        self.skills.keys().all(|skill| self.low[skill] >= self.high[skill])
    }

    fn middle(&self, skill: &str) -> Option<&'a Lesson> {
        let (low, high) = (self.low[skill], self.high[skill]);
        (low < high).then(|| self.skills[skill][(low + high) / 2])
    }

    /// The first and last task of the middle lesson of every skill still open.
    pub fn round(&self) -> Vec<Task> {
        let mut tasks = Vec::new();
        for skill in self.skills.keys() {
            if let Some(lesson) = self.middle(skill) {
                tasks.push(lesson.tasks[0].clone());
                if lesson.tasks.len() > 1 {
                    tasks.push(lesson.tasks[lesson.tasks.len() - 1].clone());
                }
            }
        }
        tasks
    }

    pub fn update(&mut self, results: &[TaskResult]) {
        let mut passed: HashMap<&str, Vec<bool>> = HashMap::new();
        for r in results {
            let grade = srs::task_grade(&r.status, r.count, r.task.reference(), r.hints);
            passed.entry(&r.task.lesson_id).or_default().push(matches!(grade, Some(srs::GOOD | srs::EASY)));
        }
        let skills: Vec<String> = self.skills.keys().cloned().collect();
        for skill in skills {
            let Some(lesson) = self.middle(&skill) else { continue };
            let Some(tries) = passed.get(lesson.id.as_str()) else { continue };
            let middle = (self.low[&skill] + self.high[&skill]) / 2;
            if tries.iter().all(|ok| *ok) {
                self.low.insert(skill, middle + 1);
            } else {
                self.high.insert(skill, middle);
            }
        }
    }

    pub fn known(&self) -> Vec<Lesson> {
        let mut found: Vec<Lesson> = self.skills.iter().flat_map(|(skill, lessons)| lessons[..self.low[skill]].iter().map(|l| (*l).clone())).collect();
        let weeks: BTreeSet<u32> = found.iter().map(|l| l.week).collect();
        for week in weeks {
            let days: Vec<&Lesson> = self.lessons.iter().filter(|l| l.week == week).collect();
            if days.iter().all(|l| l.skill == "mixed" || found.iter().any(|f| f.id == l.id)) {
                for day in days {
                    if !found.iter().any(|f| f.id == day.id) {
                        found.push(day.clone());
                    }
                }
            }
        }
        found.sort_by_key(|l| (l.week, l.day));
        found
    }
}
