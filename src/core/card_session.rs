//! One run through a queue of cards: what's asked next and how each answer grades.
//! A card you've never answered from memory is introduced: its answer is shown and
//! you type it once. A miss comes back at the end, but only the first try counts.

use super::answer::is_correct;
use super::cards::Card;
use super::progress::Progress;
use super::srs;
use std::collections::HashSet;

pub struct CardSession {
    pub queue: Vec<Card>,
    pub total: usize,
    pub retried: HashSet<String>,
    pub pending: Option<(Card, bool, String)>,
    pub intro: bool, // the card on screen is new to you
    pub correct: usize,
    pub answered: usize,
}

impl CardSession {
    pub fn new(queue: Vec<Card>) -> CardSession {
        CardSession { total: queue.len(), queue, retried: HashSet::new(), pending: None, intro: false, correct: 0, answered: 0 }
    }

    pub fn done(&self) -> usize {
        self.total - self.queue.iter().filter(|c| !self.retried.contains(&c.id)).count()
    }

    pub fn card(&self) -> Option<&Card> {
        self.queue.first()
    }

    /// The next card, and whether to introduce it.
    pub fn begin(&mut self, progress: &Progress) -> Option<Card> {
        let card = self.card()?.clone();
        // never answered from memory, and not introduced since the last miss
        self.intro = !self.retried.contains(&card.id) && !progress.ever_right(&card.id) && progress.item(&card.id).is_none_or(|item| item.reps == 0);
        Some(card)
    }

    /// False when an introduced card was copied wrong, so it's asked again.
    pub fn submit(&mut self, answer: &str) -> bool {
        let card = self.queue[0].clone();
        let correct = is_correct(answer, &card.answers, &card.style, card.case_sensitive);
        if self.intro && !correct {
            return false;
        }
        self.pending = Some((card, correct, answer.to_string()));
        true
    }

    /// "I was right": a miss the checker was too strict about.
    pub fn accept(&mut self) {
        if let Some(pending) = &mut self.pending {
            pending.1 = true;
        }
    }

    /// Grade the answered card (only the first try of a session counts).
    pub fn settle(&mut self, progress: &Progress) {
        let Some((card, correct, answer)) = self.pending.take() else { return };
        self.queue.remove(0);
        if self.intro {
            // typed with the answer shown: scheduled for tomorrow, not scored
            progress.grade(&card.id, "card", srs::GOOD);
            progress.log_card(&card, true, &answer, true); // still practice, for the streak
            return;
        }
        if self.retried.contains(&card.id) {
            return;
        }
        self.answered += 1;
        self.correct += usize::from(correct);
        progress.log_card(&card, correct, &answer, false);
        let known = progress.item(&card.id).is_some();
        let grade = if !correct { srs::AGAIN } else if known { srs::GOOD } else { srs::EASY };
        progress.grade(&card.id, "card", grade);
        if !correct {
            self.retried.insert(card.id.clone());
            self.queue.push(card);
        }
    }
}
