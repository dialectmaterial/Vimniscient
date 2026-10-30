//! Quick practice: pick a skill and a length.

use super::app::{App, Flow, Job};
use super::widgets;
use crate::core::lessons::Task;
use crate::core::missions::Mission;
use crate::core::quick;
use crate::core::today::plural;
use crossterm::event::{KeyCode, KeyEvent};
use indexmap::IndexMap;
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;

pub struct QuickScreen {
    pools: IndexMap<String, Vec<Task>>,
    mission: Option<Mission>,
    rows: Vec<(String, String, String)>, // id, title, what it holds
    at: usize,
}

impl QuickScreen {
    pub fn new(pools: IndexMap<String, Vec<Task>>, mission: Option<Mission>) -> QuickScreen {
        let mut rows = vec![(quick::NAVIGATION.to_string(), quick::title(quick::NAVIGATION), "count, find, delete the #".to_string())];
        rows.extend(pools.iter().map(|(skill, tasks)| (skill.clone(), quick::title(skill), plural(tasks.len(), "task"))));
        if let Some(mission) = &mission {
            rows.push(("mission".into(), "Mission".into(), format!("{}, across real files", mission.title)));
        }
        QuickScreen { pools, mission, rows, at: 0 }
    }

    fn start(&self, app: &mut App, minutes: u32) -> Flow {
        let id = self.rows[self.at].0.clone();
        if id == "mission" {
            app.pending = self.mission.clone().map(Job::Mission);
        } else {
            app.start_quick(&id, minutes, &self.pools);
        }
        Flow::Close
    }

    pub fn key(&mut self, app: &mut App, key: KeyEvent) -> Flow {
        match key.code {
            KeyCode::Char('1') => self.start(app, 1),
            KeyCode::Char('2') | KeyCode::Enter | KeyCode::Char('l') => self.start(app, quick::DEFAULT_MINUTES),
            KeyCode::Char('5') => self.start(app, 5),
            KeyCode::Char('j') | KeyCode::Down => {
                self.at = (self.at + 1).min(self.rows.len() - 1);
                Flow::Stay
            }
            KeyCode::Char('k') | KeyCode::Up => {
                self.at = self.at.saturating_sub(1);
                Flow::Stay
            }
            KeyCode::Esc | KeyCode::Char('h') | KeyCode::Char('q') => Flow::Close,
            _ => Flow::Stay,
        }
    }

    pub fn draw(&self, frame: &mut Frame, app: &App) {
        let t = &app.theme;
        let [space, bar] = Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).areas(frame.area());
        let lines: Vec<Line> = self.rows.iter().enumerate().map(|(i, (_, title, what))| {
            let line = format!(" {} {what}", widgets::fit(title, 14));
            let filled = widgets::fit(&line, 70); // the highlight runs across the column
            let first = filled.chars().take(16).collect::<String>();
            let rest = filled.chars().skip(16).collect::<String>();
            let row = Line::from(vec![Span::raw(first), Span::styled(rest, Style::new().fg(t.muted))]);
            if i == self.at { row.style(Style::new().bg(t.selected)) } else { row }
        }).collect();
        let area = widgets::centred(space, 76, lines.len() as u16 + 4);
        frame.render_widget(Paragraph::new(lines).block(widgets::column("Quick practice", t)), area);
        let keys = [("1", "minute"), ("2", "minutes"), ("5", "minutes"), ("⏎", "2 minutes"), ("esc", "back")];
        frame.render_widget(Paragraph::new(widgets::keybar(&keys, t)), bar);
    }
}
