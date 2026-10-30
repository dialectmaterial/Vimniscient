//! The app: its screens, what's running, and the steps of today.

use super::cards::CardScreen;
use super::drills::DrillScreen;
use super::lesson::{Intro, Results};
use super::main_screen::MainScreen;
use super::quick::QuickScreen;
use super::stats::StatsScreen;
use super::theme::{self, Theme};
use super::{Message, text, widgets};
use crate::core::cards::{Deck, has_lazyvim, load_decks};
use crate::core::drills::{Drill, load_drills};
use crate::core::lessons::{LESSONS, Lesson, two_rounds};
use crate::core::missions::{self, Mission};
use crate::core::placement::{self, Search};
use crate::core::progress::{Progress, today as date};
use crate::core::results::TaskResult;
use crate::core::today::{self, Step, Work};
use crate::core::{endless, quick, settings, transfer};
use crate::system::vimgolf::{self, Challenge};
use crate::system::{nvim, reminders};
use chrono::Local;
use crossterm::event::KeyEvent;
use indexmap::IndexMap;
use ratatui::Frame;
use ratatui::style::Style;
use ratatui::text::Line;
use ratatui::widgets::{Block, Clear, Paragraph};
use std::collections::VecDeque;
use std::sync::mpsc::{Receiver, Sender, channel};
use std::time::{Duration, Instant};

/// What a screen wants after a key.
#[derive(PartialEq)]
pub enum Flow {
    Stay,
    Close,
}

pub enum Screen {
    Main(MainScreen),
    Intro(Intro),
    Results(Results),
    Cards(CardScreen),
    Drills(DrillScreen),
    Quick(QuickScreen),
    Stats(StatsScreen),
}

/// Something that runs in Neovim, away from the interface.
#[derive(Clone)]
pub enum Job {
    Lesson(Lesson),
    Review(Lesson),
    Placement,
    Golf(Challenge),
    Endless(usize),
    Transfer(Vec<transfer::Challenge>),
    Quick(Lesson),
    Mission(Mission),
}

pub struct App {
    pub theme: Theme,
    pub lessons: &'static [Lesson],
    pub progress: Progress,
    pub decks: IndexMap<String, Deck>,
    pub drills: Vec<Drill>,
    pub screens: Vec<Screen>,
    pub pending: Option<Job>,
    pub quit: bool,
    pub messages: (Sender<Message>, Receiver<Message>),
    toast: Option<(String, Instant)>,
    queue: VecDeque<String>, // the routine steps still to start, after `t`
    routine: bool,
    placement: Option<Search<'static>>,
}

impl App {
    pub fn new() -> App {
        // Week 5 teaches LazyVim's own text objects; without LazyVim it's left out.
        let lessons: Vec<Lesson> = LESSONS.iter().filter(|l| !l.lazyvim || has_lazyvim()).cloned().collect();
        Self::with(Box::leak(lessons.into_boxed_slice()), load_decks())
    }

    pub fn with(lessons: &'static [Lesson], decks: IndexMap<String, Deck>) -> App {
        let progress = Progress::open().unwrap_or_else(|error| {
            eprintln!("vimniscient: can't open your progress: {error}");
            std::process::exit(1);
        });
        let theme = theme::omarchy_theme();
        if let Ok(mut colors) = nvim::COLORS.lock() {
            *colors = Some(theme::lesson_colors(&theme));
        }
        let mut app = App {
            theme, lessons, progress, decks, drills: load_drills(), screens: Vec::new(), pending: None, quit: false, messages: channel(),
            toast: None, queue: VecDeque::new(), routine: false, placement: None,
        };
        let main = MainScreen::new(&app);
        app.screens.push(Screen::Main(main));
        app
    }

    pub fn work(&self) -> Work {
        today::todays_work(&self.progress, self.lessons, &self.decks, &self.drills, None)
    }

    pub fn plan(&self) -> Vec<Step> {
        today::plan(&self.progress, self.lessons, &self.work())
    }

    pub fn notify(&mut self, text: impl Into<String>) {
        self.toast = Some((text.into(), Instant::now()));
    }

    pub fn push(&mut self, screen: Screen) {
        self.screens.push(screen);
    }

    pub fn draw(&self, frame: &mut Frame) {
        let area = frame.area();
        frame.render_widget(Block::new().style(Style::new().bg(self.theme.background).fg(self.theme.foreground)), area);
        match self.screens.last() {
            Some(Screen::Main(s)) => s.draw(frame, self),
            Some(Screen::Intro(s)) => s.draw(frame, self),
            Some(Screen::Results(s)) => s.draw(frame, self),
            Some(Screen::Cards(s)) => s.draw(frame, self),
            Some(Screen::Drills(s)) => s.draw(frame, self),
            Some(Screen::Quick(s)) => s.draw(frame, self),
            Some(Screen::Stats(s)) => s.draw(frame, self),
            None => {}
        }
        if let Some((text, _)) = &self.toast {
            let width = (text.chars().count() as u16 + 4).min(area.width);
            let rect = ratatui::layout::Rect::new(area.width - width, area.height.saturating_sub(4), width, 3.min(area.height));
            frame.render_widget(Clear, rect);
            frame.render_widget(Paragraph::new(Line::from(text.clone())).block(widgets::plain(true, &self.theme)), rect);
        }
    }

    pub fn press(&mut self, key: KeyEvent) {
        let Some(mut held) = self.screens.pop() else { return };
        let depth = self.screens.len();
        let flow = match &mut held {
            Screen::Main(s) => s.key(self, key),
            Screen::Intro(s) => s.key(self, key),
            Screen::Results(s) => s.key(self, key),
            Screen::Cards(s) => s.key(self, key),
            Screen::Drills(s) => s.key(self, key),
            Screen::Quick(s) => s.key(self, key),
            Screen::Stats(s) => s.key(key),
        };
        // a screen a key opened goes on top of the one that opened it
        let opened = self.screens.split_off(depth);
        let closed = flow == Flow::Close;
        if !closed {
            self.screens.push(held);
        } else if let Screen::Results(results) = &held
            && matches!(results.job, Some(Job::Placement))
            && self.pending.is_none()
            && self.placement.as_ref().is_some_and(|search| !search.finished())
        {
            self.pending = Some(Job::Placement);
        } else if let Screen::Drills(drills) = &mut held {
            drills.close();
        }
        self.screens.extend(opened);
        if closed {
            self.back();
        }
    }

    /// Back on the main screen: fresh numbers, and on to the next step of today.
    fn back(&mut self) {
        if self.screens.len() != 1 {
            return;
        }
        if let Some(Screen::Main(mut main)) = self.screens.pop() {
            main.refresh(self);
            self.screens.push(Screen::Main(main));
        }
        self.advance();
    }

    fn advance(&mut self) {
        if self.pending.is_some() || self.screens.len() > 1 {
            return;
        }
        while let Some(id) = self.queue.pop_front() {
            if self.step(&id, false) {
                return;
            }
        }
        if self.routine {
            self.routine = false;
            if today::left(&self.plan()).is_empty() {
                self.notify("That's today's practice done. See you tomorrow.");
            }
        }
    }

    /// Start a step of today. `direct` skips the intro (the main screen shows it already).
    fn step(&mut self, id: &str, direct: bool) -> bool {
        match id {
            "cards" => {
                let cards = self.work().cards;
                if cards.is_empty() {
                    return false;
                }
                let screen = CardScreen::new(cards, "Today's cards");
                self.push(Screen::Cards(screen));
            }
            "drills" => {
                let drills = self.work().drills;
                if drills.is_empty() {
                    return false;
                }
                self.open_drills(drills);
            }
            "review" => {
                let review = self.work().review;
                if review.is_empty() {
                    return false;
                }
                self.lesson_or_intro(text::review_lesson(review), Job::Review, direct);
            }
            "lesson" => {
                let Some(lesson) = self.progress.next_lesson(self.lessons).cloned() else { return false };
                self.lesson_or_intro(lesson, Job::Lesson, direct);
            }
            "vimgolf" => {
                if self.progress.vimgolf_done_today() {
                    return false;
                }
                self.start_vimgolf();
            }
            "quick" => self.open_quick(),
            "transfer" => {
                let picks = transfer::pick(self.lessons, &self.progress);
                if picks.is_empty() {
                    return false;
                }
                self.pending = Some(Job::Transfer(picks));
            }
            "endless" => {
                let start = self.progress.endless_start(endless::RESTART_BELOW);
                if direct {
                    self.pending = Some(Job::Endless(start));
                } else {
                    let lesson = text::endless_lesson(start, self.progress.endless_best());
                    self.push(Screen::Intro(Intro::new(lesson, Job::Endless(start), self)));
                }
            }
            _ => return false,
        }
        true
    }

    fn lesson_or_intro(&mut self, lesson: Lesson, job: fn(Lesson) -> Job, direct: bool) {
        if direct {
            self.pending = Some(job(lesson));
        } else {
            let intro = Intro::new(lesson.clone(), job(lesson), self);
            self.push(Screen::Intro(intro));
        }
    }

    pub fn run_step(&mut self, id: &str, direct: bool) {
        if !self.step(id, direct) {
            self.notify("Nothing left for this one today.");
        }
    }

    /// Cards, drills, review, then the next lesson: whichever are still left today.
    pub fn start_today(&mut self) {
        let plan = self.plan();
        let left: Vec<String> = today::left(&plan).iter().map(|s| s.id.clone()).filter(|id| today::ROUTINE.contains(&id.as_str())).collect();
        if left.is_empty() {
            self.notify("That's everything for today. Endless (e) or any lesson if you want more.");
            return;
        }
        self.queue = left.into();
        self.routine = true;
        self.advance();
    }

    pub fn open_cards(&mut self) {
        let mut cards = self.progress.due_cards(&self.decks, self.lessons, Some(30));
        cards.extend(self.progress.new_cards(&self.decks, self.lessons));
        if cards.is_empty() {
            self.notify("No cards due. Come back tomorrow.");
        } else {
            self.push(Screen::Cards(CardScreen::new(cards, "Cards")));
        }
    }

    pub fn open_all_drills(&mut self) {
        let todays = self.work().drills;
        let drills = if todays.is_empty() { self.drills.clone() } else { todays };
        self.open_drills(drills);
    }

    fn open_drills(&mut self, drills: Vec<Drill>) {
        if crate::system::hyprland::available() {
            let screen = DrillScreen::new(drills, self);
            self.push(Screen::Drills(screen));
        } else {
            self.notify("No Hyprland session found, so no drills.");
        }
    }

    pub fn open_quick(&mut self) {
        let done = self.progress.done(self.lessons);
        let pools = quick::pools(self.lessons, &done);
        let mission = missions::pick(self.lessons, &self.progress);
        self.push(Screen::Quick(QuickScreen::new(pools, mission)));
    }

    pub fn start_quick(&mut self, skill: &str, minutes: u32, pools: &IndexMap<String, Vec<crate::core::lessons::Task>>) {
        let count = quick::how_many(minutes, self.progress.typical_task_seconds());
        let tasks = quick::build(skill, count, pools, &self.lessons[0].tasks[0], &Local::now().to_rfc3339());
        self.pending = Some(Job::Quick(text::quick_lesson(&quick::title(skill), tasks)));
    }

    pub fn open_placement(&mut self) {
        let search = Search::new(self.lessons, None);
        let lesson = text::placement_lesson(search.round());
        self.placement = Some(search);
        self.push(Screen::Intro(Intro::new(lesson, Job::Placement, self)));
    }

    pub fn open_stats(&mut self) {
        let stats = StatsScreen::new(self);
        self.push(Screen::Stats(stats));
    }

    pub fn start_vimgolf(&mut self) {
        self.notify("Fetching today's VimGolf challenge…");
        let out = self.messages.0.clone();
        std::thread::spawn(move || {
            // A thread of its own: a database connection can't cross threads, so it opens one.
            let found = Progress::open().map_err(|e| e.to_string()).and_then(|progress| vimgolf::today(&progress));
            let _ = out.send(Message::Golf(found));
        });
    }

    /// What happens between keys: messages from other threads, timers, old notices.
    pub fn tick(&mut self) {
        while let Ok(message) = self.messages.1.try_recv() {
            match message {
                Message::Hyprland(line) => {
                    if let Some(Screen::Drills(mut drills)) = self.screens.pop() {
                        drills.event(self, &line);
                        self.screens.push(Screen::Drills(drills));
                    }
                }
                Message::Golf(Ok(Some(challenge))) => {
                    let lesson = text::vimgolf_lesson(&challenge);
                    self.push(Screen::Intro(Intro::new(lesson, Job::Golf(challenge), self)));
                }
                Message::Golf(Ok(None)) => {
                    self.notify("No VimGolf challenges left to try.");
                    self.advance();
                }
                Message::Golf(Err(error)) => {
                    self.notify(format!("Couldn't get a VimGolf challenge ({error}). Skipping it."));
                    self.advance();
                }
            }
        }
        if let Some(Screen::Drills(mut drills)) = self.screens.pop_if(|s| matches!(s, Screen::Drills(_))) {
            let flow = drills.tick(self);
            if flow == Flow::Stay {
                self.screens.push(Screen::Drills(drills));
            } else {
                self.back();
            }
        }
        if self.toast.as_ref().is_some_and(|(_, shown)| shown.elapsed() > Duration::from_secs(4)) {
            self.toast = None;
        }
    }

    /// Run `job` in Neovim, store the results and show them. Blocks until Neovim quits.
    pub fn execute(&mut self, job: Job) {
        let day = date().to_string();
        let (lesson, results, note, subtitle, again) = match job.clone() {
            Job::Lesson(lesson) => {
                let mut session = lesson.clone();
                session.tasks = two_rounds(&lesson, &day);
                let results = nvim::run_lesson(&session, true);
                self.progress.record(&results);
                (session, results, String::new(), String::new(), job)
            }
            Job::Review(lesson) => {
                let results = nvim::run_lesson(&lesson, true);
                self.progress.record(&results);
                (lesson, results, String::new(), String::new(), job)
            }
            Job::Placement => {
                let Some(search) = &mut self.placement else { return };
                let lesson = text::placement_lesson(search.round());
                let results = nvim::run_lesson(&lesson, false);
                self.progress.record(&results);
                search.update(&results);
                search.seen.extend(results.iter().map(|r| r.task.item_id()));
                let note = if search.finished() {
                    let known = search.known();
                    self.progress.mark_known(&known, &search.seen);
                    placement::note(&known)
                } else {
                    placement::NEXT_ROUND.to_string()
                };
                (lesson, results, note, String::new(), job)
            }
            Job::Golf(challenge) => {
                let lesson = text::vimgolf_lesson(&challenge);
                let results = nvim::run_lesson(&lesson, false);
                let note = match results.first().and_then(|r| self.progress.record_vimgolf(&challenge.id, r, vimgolf::SAVE_KEYS)) {
                    None => format!("Not solved. It stays today's challenge. ({})", challenge.url()),
                    Some(score) => {
                        let best = challenge.best.map_or(String::new(), |b| format!(", best on vimgolf.com {b}"));
                        format!("Your VimGolf score: {score} (keys + ZZ){best}. Solutions: {}", challenge.url())
                    }
                };
                (lesson, results, note, String::new(), job)
            }
            Job::Endless(start) => {
                let best = self.progress.endless_best();
                let rungs = endless::ladder(self.lessons, start, &Local::now().to_rfc3339());
                let results = nvim::run_endless(&rungs, start, endless::RAMP, endless::GAP);
                let run = endless::summary(&results, start);
                self.progress.record_endless(&results, &run);
                let again = Job::Endless(self.progress.endless_start(endless::RESTART_BELOW));
                (text::endless_lesson(start, best), results, endless::note(&run, best), format!("level {}", run.level), again)
            }
            Job::Transfer(picks) => {
                let lesson = text::transfer_lesson(picks.iter().map(|c| c.task.clone()).collect());
                let results = nvim::run_lesson(&lesson, false);
                self.progress.record_ungraded(&results, "transfer");
                let note = transfer::note(&picks, &results);
                (lesson, results, note, String::new(), job)
            }
            Job::Quick(lesson) => {
                let results = nvim::run_lesson(&lesson, false);
                self.progress.record_ungraded(&results, "quick");
                (lesson, results, String::new(), String::new(), job)
            }
            Job::Mission(mission) => {
                let result = nvim::run_mission(&mission);
                self.progress.record_ungraded(std::slice::from_ref(&result), "mission");
                let note = mission.note(result.status == "solved");
                (text::mission_lesson(&mission), vec![result], note, String::new(), job)
            }
        };
        self.show_results(lesson, results, note, subtitle, Some(again));
    }

    pub fn show_results(&mut self, lesson: Lesson, results: Vec<TaskResult>, note: String, subtitle: String, job: Option<Job>) {
        let screen = Results::new(&lesson, results, note, subtitle, job, self);
        self.push(Screen::Results(screen));
    }

    /// Done for the day? Then the reminders still waiting can go.
    pub fn leave(&self) {
        reminders::sync(&self.plan());
    }

    pub fn budget_minutes(&self) -> u32 {
        settings::minutes()
    }
}
