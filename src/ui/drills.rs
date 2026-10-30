//! The live Omarchy drill screen: do it for real, the event socket confirms it.

use super::app::{App, Flow};
use super::widgets;
use crate::core::drills::{self, Drill, DrillRun};
use crate::system::hyprland;
use crossterm::event::{KeyCode, KeyEvent};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Paragraph, Wrap};
use std::process::Child;
use std::time::{Duration, Instant};

const AUTO_HINT_SECONDS: u64 = 25;

pub struct DrillScreen {
    queue: Vec<Drill>,
    total: usize,
    home: String,
    window: Option<Child>,
    current: Option<DrillRun>,
    hinted: bool,
    status: Vec<Span<'static>>,
    next_at: Option<Instant>, // the next drill loads at this moment
}

impl DrillScreen {
    pub fn new(queue: Vec<Drill>, app: &App) -> DrillScreen {
        hyprland::listen(app.messages.0.clone());
        DrillScreen { total: queue.len(), queue, home: hyprland::home(), window: None, current: None, hinted: false, status: vec![Span::raw("Opening the drill window…")], next_at: Some(Instant::now()) }
    }

    fn next_drill(&mut self, app: &mut App) -> Flow {
        let Some(drill) = self.queue.first().cloned() else { return Flow::Close };
        let Some(address) = hyprland::ensure_drill_window(&mut self.window) else {
            app.notify("Couldn't open the drill window.");
            return Flow::Close;
        };
        self.current = Some(DrillRun::new(drill, address, self.home.clone()));
        self.hinted = false;
        Flow::Stay
    }

    fn hint(&self, app: &App) -> Vec<Span<'static>> {
        let Some(run) = &self.current else { return Vec::new() };
        let t = &app.theme;
        let cards = app.decks.get("omarchy").map(|d| d.cards.as_slice()).unwrap_or_default();
        let mut spans = Vec::new();
        for binding in &run.drill.bindings {
            if let Some(card) = cards.iter().find(|c| &c.prompt == binding) {
                if !spans.is_empty() {
                    spans.push(Span::raw(" · "));
                }
                spans.push(Span::raw(format!("{binding}: ")));
                spans.push(Span::styled(card.answers.join(", "), Style::new().fg(t.foreground).add_modifier(Modifier::BOLD)));
            }
        }
        if spans.is_empty() {
            spans.push(Span::raw("see SUPER + K"));
        }
        if run.drill.bindings.iter().any(|b| b.ends_with(" 1")) {
            spans.push(Span::raw(" (1 stands for any number)"));
        }
        spans
    }

    fn finish(&mut self, app: &mut App, skipped: bool) {
        let Some(run) = &self.current else { return };
        let seconds = run.started.elapsed().as_secs_f64();
        app.progress.grade(&run.drill.item_id(), "drill", drills::grade(seconds, self.hinted, skipped));
        app.progress.log_drill(&run.drill.id, seconds, self.hinted, skipped);
        self.queue.remove(0);
        let t = &app.theme;
        if skipped {
            let mut status = vec![Span::styled("Skipped. ", Style::new().fg(t.warning))];
            status.extend(self.hint(app));
            self.status = status;
        } else {
            self.status = vec![Span::styled(format!("Done in {seconds:.0}s."), Style::new().fg(t.success))];
        }
        self.next_at = Some(Instant::now() + Duration::from_millis(if skipped { 3000 } else { 1500 }));
    }

    pub fn event(&mut self, app: &mut App, line: &str) {
        let Some(run) = &mut self.current else { return };
        if !run.finished() && run.feed(line) && run.finished() {
            self.finish(app, false);
        }
    }

    pub fn tick(&mut self, app: &mut App) -> Flow {
        if self.next_at.is_some_and(|at| Instant::now() >= at) {
            self.next_at = None;
            if self.next_drill(app) == Flow::Close {
                self.close();
                return Flow::Close;
            }
        }
        let Some(run) = &self.current else { return Flow::Stay };
        if run.finished() {
            return Flow::Stay;
        }
        let seconds = run.started.elapsed().as_secs();
        if seconds >= AUTO_HINT_SECONDS {
            self.hinted = true;
        }
        let dim = Style::new().fg(app.theme.muted);
        let mut status = vec![Span::styled(format!("{seconds}s  "), dim)];
        if self.hinted {
            status.extend(self.hint(app));
        } else {
            status.push(Span::styled("waiting for Hyprland…", dim));
        }
        self.status = status;
        Flow::Stay
    }

    pub fn key(&mut self, app: &mut App, key: KeyEvent) -> Flow {
        let running = self.current.as_ref().is_some_and(|run| !run.finished());
        match key.code {
            KeyCode::Char('h') if running => self.hinted = true,
            KeyCode::Char('s') if running => {
                if let Some(run) = &mut self.current {
                    run.step = run.drill.steps.len(); // stop listening for this one
                }
                self.finish(app, true);
            }
            KeyCode::Esc => {
                self.close();
                return Flow::Close;
            }
            _ => {}
        }
        Flow::Stay
    }

    pub fn close(&mut self) {
        self.current = None;
        hyprland::close_drill_window(&mut self.window);
    }

    pub fn draw(&self, frame: &mut Frame, app: &App) {
        let t = &app.theme;
        let [space, bar] = Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).areas(frame.area());
        let done = self.total - self.queue.len();
        let mut lines = vec![widgets::progress_bar(done, self.total, t), Line::default()];
        let mut title = "Omarchy drills".to_string();
        if let Some(run) = &self.current {
            title = format!("Omarchy drills · {}", run.drill.title);
            lines.push(Line::styled(run.text(&run.drill.prompt), Style::new().fg(t.primary).add_modifier(Modifier::BOLD)));
            lines.push(Line::default());
            for (i, step) in run.drill.steps.iter().enumerate() {
                let (mark, color) = if i < run.step { ("✓", t.success) } else if i == run.step { ("›", t.accent) } else { ("·", t.muted) };
                lines.push(Line::from(vec![Span::styled(format!("{mark}  "), Style::new().fg(color)), Span::raw(run.text(&step.done))]));
            }
            let last = run.drill.steps[run.step.min(run.drill.steps.len() - 1)].active.as_deref() == Some("$drill");
            if last || run.drill.id == "float" {
                lines.push(Line::default());
                lines.push(Line::styled("Do it to the window titled “Vimniscient drill” (focus it first).", Style::new().fg(t.muted)));
            }
            lines.push(Line::default());
        }
        lines.push(Line::from(self.status.clone()));
        let inner = 76.min(space.width).saturating_sub(6);
        let area = widgets::centred(space, 76, widgets::wrapped_height(&lines, inner) + 4);
        let block = widgets::caption(widgets::column(&title, t), &format!("{}/{}", (done + 1).min(self.total), self.total), true, t);
        frame.render_widget(Paragraph::new(lines).wrap(Wrap { trim: false }).block(block), area);
        frame.render_widget(Paragraph::new(widgets::keybar(&[("h", "hint"), ("s", "skip"), ("esc", "stop")], t)), bar);
    }
}
