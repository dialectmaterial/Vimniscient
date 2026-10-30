//! The main screen, lazygit-style: Today and Lessons on the left, the highlighted entry
//! on the right, progress below it. Tab moves between panes.

use super::app::{App, Flow, Job};
use super::theme::Theme;
use super::{markdown, text, widgets};
use crate::core::cards::has_plugin;
use crate::core::progress::today as date;
use crate::core::today::{self, Step};
use crate::core::habits;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::symbols::bar;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Paragraph, Sparkline, Wrap};
use std::cell::Cell;

struct Row {
    id: Option<String>, // None for a week heading
    line: Line<'static>,
}

pub struct MainScreen {
    lessons_focused: bool,
    plan: Vec<Step>,
    plan_at: usize,
    footer: String,
    rows: Vec<Row>,
    row_at: usize,
    offset: Cell<usize>,
    detail_title: String,
    detail: Vec<Line<'static>>,
    progress: Vec<Line<'static>>,
    spark: Vec<u64>,
}

impl MainScreen {
    pub fn new(app: &App) -> MainScreen {
        let mut screen = MainScreen {
            lessons_focused: false, plan: Vec::new(), plan_at: 0, footer: String::new(), rows: Vec::new(), row_at: usize::MAX,
            offset: Cell::new(0), detail_title: String::new(), detail: Vec::new(), progress: Vec::new(), spark: Vec::new(),
        };
        screen.refresh(app);
        screen
    }

    pub fn refresh(&mut self, app: &App) {
        self.plan = app.plan();
        self.footer = today::left_text(&self.plan, app.budget_minutes());
        self.plan_at = self.plan_at.min(self.plan.len().saturating_sub(1));
        self.refresh_lessons(app);
        self.refresh_progress(app);
        self.show_detail(app);
    }

    fn refresh_lessons(&mut self, app: &App) {
        let t = &app.theme;
        let dim = Style::new().fg(t.muted);
        let (mut rows, mut week) = (Vec::new(), 0);
        for lesson in app.lessons {
            if lesson.week != week {
                week = lesson.week;
                rows.push(Row { id: None, line: Line::styled(format!("Week {week}"), dim) });
            }
            let best = app.progress.best(lesson);
            let (mark, color, count) = if best.len() == lesson.tasks.len() {
                ("✓", t.success, String::new())
            } else if app.progress.is_placed(lesson) {
                ("○", t.success, String::new())
            } else if !best.is_empty() {
                ("◐", t.primary, format!(" {}/{}", best.len(), lesson.tasks.len()))
            } else {
                ("·", t.muted, String::new())
            };
            let line = Line::from(vec![Span::raw(" "), Span::styled(mark, Style::new().fg(color)), Span::raw(format!(" {} {}", lesson.day, lesson.title)), Span::styled(count, dim)]);
            rows.push(Row { id: Some(lesson.id.clone()), line });
        }
        if self.row_at >= rows.len() {
            let next = app.progress.next_lesson(app.lessons).map(|l| l.id.clone());
            self.row_at = rows.iter().position(|r| r.id == next && next.is_some()).or_else(|| rows.iter().position(|r| r.id.is_some())).unwrap_or(0);
        }
        self.rows = rows;
    }

    fn refresh_progress(&mut self, app: &App) {
        let (t, progress, lessons) = (&app.theme, &app.progress, app.lessons);
        let dim = Style::new().fg(t.muted);
        let bold = Style::new().add_modifier(Modifier::BOLD);
        let done = lessons.iter().filter(|l| progress.is_done(l)).count();
        let streak = progress.streak();
        let mut parts = vec![if streak > 0 {
            vec![Span::styled(format!("{streak}-day"), bold), Span::raw(" streak")]
        } else {
            vec![Span::raw("no streak yet")]
        }];
        parts.push(vec![Span::styled(format!("{done}/{}", lessons.len()), bold), Span::raw(" lessons")]);
        if progress.endless_best() > 0 {
            parts.push(vec![Span::raw(format!("endless best level {}", progress.endless_best()))]);
        }
        let blocks = progress.sync_hardtime(lessons);
        if has_plugin("hardtime.nvim") {
            let earliest = progress.hardtime_earliest().max(date());
            parts.push(vec![Span::raw(if blocks { "hardtime blocking".to_string() } else { format!("hardtime blocks after week 2, from {} at the earliest", earliest.format("%b %d")) })]);
        }
        let mut first = Vec::new();
        for (i, part) in parts.into_iter().enumerate() {
            if i > 0 {
                first.push(Span::raw(" · "));
            }
            first.extend(part);
        }
        let mut lines = vec![Line::from(first)];
        if let Some(top) = habits::habits(14).into_iter().find(|h| h.recent > 0) {
            lines.push(Line::from(vec![Span::styled("top habit: ", dim), Span::raw(format!("{} ({}×)", top.message, top.recent))]));
        }
        if progress.days_trained().is_empty() {
            lines.push(Line::from(vec![Span::styled("New here? Press ", dim), Span::styled("p", bold.fg(t.primary)), Span::styled(" for the placement test: it skips what you know.", dim)]));
        }
        let days = progress.efficiency_by_day(14);
        self.spark = days.iter().rev().filter(|d| d.2 > 0).map(|d| (100 * d.3 / d.2) as u64).collect();
        lines.push(Line::styled(if self.spark.is_empty() { "efficiency shows up after your first lesson" } else { "keystroke efficiency, last 14 days" }, dim));
        self.progress = lines;
    }

    /// The right pane follows whichever list has focus.
    fn show_detail(&mut self, app: &App) {
        let id = if self.lessons_focused { self.rows.get(self.row_at).and_then(|r| r.id.clone()) } else { None };
        let step = self.plan.get(self.plan_at).map_or("", |s| s.id.as_str());
        let lesson = if self.lessons_focused {
            app.lessons.iter().find(|l| Some(&l.id) == id.as_ref())
        } else if step == "lesson" {
            app.progress.next_lesson(app.lessons)
        } else {
            None
        };
        let (title, body) = match lesson {
            Some(lesson) => (format!("{} · {}", lesson.label(), lesson.title), text::lesson_markdown(lesson, Some(&app.progress.best(lesson)))),
            None if step == "lesson" && !self.lessons_focused => ("Lessons".to_string(), "Every lesson is done. Pick any in the Lessons list to practise again.".to_string()),
            None => {
                let (title, body) = text::plan_detail(step);
                (title.to_string(), body)
            }
        };
        self.detail_title = title;
        self.detail = markdown::render(&body, &app.theme);
    }

    fn move_by(&mut self, step: isize, app: &App) {
        if self.lessons_focused {
            let mut at = self.row_at as isize + step;
            while at >= 0 && (at as usize) < self.rows.len() {
                if self.rows[at as usize].id.is_some() {
                    self.row_at = at as usize;
                    break;
                }
                at += step;
            }
        } else {
            self.plan_at = (self.plan_at as isize + step).clamp(0, self.plan.len() as isize - 1) as usize;
        }
        self.show_detail(app);
    }

    fn focus(&mut self, lessons: bool, app: &App) {
        self.lessons_focused = lessons;
        self.show_detail(app);
    }

    fn open(&mut self, app: &mut App) {
        if self.lessons_focused {
            let id = self.rows.get(self.row_at).and_then(|r| r.id.clone());
            if let Some(lesson) = app.lessons.iter().find(|l| Some(&l.id) == id.as_ref()) {
                app.pending = Some(Job::Lesson(lesson.clone()));
            }
        } else if let Some(step) = self.plan.get(self.plan_at) {
            let id = step.id.clone();
            app.run_step(&id, true);
        }
    }

    pub fn key(&mut self, app: &mut App, key: KeyEvent) -> Flow {
        if key.modifiers.contains(KeyModifiers::CONTROL) {
            if key.code == KeyCode::Char('c') {
                app.quit = true;
            }
            return Flow::Stay;
        }
        match key.code {
            KeyCode::Char('t') => app.start_today(),
            KeyCode::Char('c') => app.open_cards(),
            KeyCode::Char('d') => app.open_all_drills(),
            KeyCode::Char('e') => app.run_step("endless", false),
            KeyCode::Char('g') => app.start_vimgolf(),
            KeyCode::Char('z') => app.open_quick(),
            KeyCode::Char('x') => app.run_step("transfer", false),
            KeyCode::Char('p') => app.open_placement(),
            KeyCode::Char('s') => app.open_stats(),
            KeyCode::Char('1') => self.focus(false, app),
            KeyCode::Char('2') => self.focus(true, app),
            KeyCode::Tab | KeyCode::BackTab => self.focus(!self.lessons_focused, app),
            KeyCode::Char('j') | KeyCode::Down => self.move_by(1, app),
            KeyCode::Char('k') | KeyCode::Up => self.move_by(-1, app),
            KeyCode::Char('l') | KeyCode::Enter => self.open(app),
            KeyCode::Char('q') => app.quit = true,
            _ => {}
        }
        Flow::Stay
    }

    fn draw_plan(&self, frame: &mut Frame, area: Rect, t: &Theme) {
        let focused = !self.lessons_focused;
        let block = widgets::caption(widgets::pane("1 Today", focused, t), &self.footer, focused, t);
        let lines: Vec<Line> = self.plan.iter().enumerate().map(|(i, step)| {
            let (mark, color) = match (step.id.as_str(), step.todo) {
                ("endless", None) => ("∞", t.secondary),
                (_, None) => ("·", t.secondary),
                (_, Some(true)) => ("›", t.primary),
                _ => ("✓", t.success),
            };
            let line = Line::from(vec![
                Span::raw(" "),
                Span::styled(mark, Style::new().fg(color)),
                Span::styled(format!(" {:<8} ", step.label), Style::new().add_modifier(Modifier::BOLD)),
                Span::styled(step.detail.clone(), Style::new().fg(t.muted)),
            ]);
            if i == self.plan_at { line.style(Style::new().bg(if focused { t.selected } else { t.surface })) } else { line }
        }).collect();
        frame.render_widget(Paragraph::new(lines).block(block), area);
    }

    fn draw_lessons(&self, frame: &mut Frame, area: Rect, t: &Theme) {
        let focused = self.lessons_focused;
        let height = area.height.saturating_sub(2) as usize;
        let mut offset = self.offset.get();
        if self.row_at < offset {
            offset = self.row_at;
        } else if self.row_at >= offset + height.max(1) {
            offset = self.row_at + 1 - height.max(1);
        }
        self.offset.set(offset);
        let lines: Vec<Line> = self.rows.iter().enumerate().skip(offset).take(height).map(|(i, row)| {
            let line = row.line.clone();
            if i == self.row_at { line.style(Style::new().bg(if focused { t.selected } else { t.surface })) } else { line }
        }).collect();
        frame.render_widget(Paragraph::new(lines).block(widgets::pane("2 Lessons", focused, t)), area);
    }

    pub fn draw(&self, frame: &mut Frame, app: &App) {
        let t = &app.theme;
        let [main, bar_area] = Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).areas(frame.area());
        let left_width = 46.min(main.width * 45 / 100);
        let [left, right] = Layout::horizontal([Constraint::Length(left_width), Constraint::Min(0)]).areas(main);
        let [plan, lessons] = Layout::vertical([Constraint::Length(10), Constraint::Min(0)]).areas(left);
        self.draw_plan(frame, plan, t);
        self.draw_lessons(frame, lessons, t);

        let inner = right.width.saturating_sub(4);
        let spark_rows = if self.spark.is_empty() { 0 } else { 3 };
        let progress_height = (widgets::wrapped_height(&self.progress, inner) + spark_rows + 2).min(10);
        let [detail, progress] = Layout::vertical([Constraint::Min(0), Constraint::Length(progress_height)]).areas(right);
        let body = Paragraph::new(self.detail.clone()).wrap(Wrap { trim: false }).block(widgets::pane(&self.detail_title, false, t).padding(ratatui::widgets::Padding::horizontal(1)));
        frame.render_widget(body, detail);
        let block = widgets::pane("Progress", false, t).padding(ratatui::widgets::Padding::horizontal(1));
        let inside = block.inner(progress);
        frame.render_widget(block, progress);
        let [words, _, spark] = Layout::vertical([Constraint::Min(0), Constraint::Length(u16::from(spark_rows > 0)), Constraint::Length(spark_rows.min(2))]).areas(inside);
        frame.render_widget(Paragraph::new(self.progress.clone()).wrap(Wrap { trim: false }), words);
        frame.render_widget(Sparkline::default().data(&self.spark).bar_set(bar::NINE_LEVELS).style(Style::new().fg(t.primary)), spark);
        let keys = [("t", "today"), ("⏎", "open"), ("⇥", "pane"), ("z", "quick"), ("x", "choose"), ("e", "endless"), ("c", "cards"), ("d", "drills"), ("g", "golf"), ("p", "place"), ("s", "stats"), ("q", "quit")];
        frame.render_widget(Paragraph::new(widgets::keybar(&keys, t)), bar_area);
    }
}
