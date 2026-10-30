//! The stats screen: progress tables.

use super::app::{App, Flow};
use super::theme::Theme;
use super::widgets;
use crate::core::progress::today;
use crate::core::today::plural;
use crate::core::habits;
use crate::system::hyprland;
use crossterm::event::{KeyCode, KeyEvent};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Padding, Paragraph};

pub struct StatsScreen {
    lines: Vec<Line<'static>>,
    scroll: u16,
}

/// A table as lines: each column as wide as its widest cell, up to `limit`.
fn table(lines: &mut Vec<Line<'static>>, label: &str, header: &[&str], rows: Vec<Vec<String>>, t: &Theme) {
    const LIMIT: usize = 56;
    let dim = Style::new().fg(t.muted);
    lines.push(Line::default());
    lines.push(Line::styled(label.to_string(), dim.add_modifier(Modifier::BOLD)));
    lines.push(Line::default());
    let mut widths: Vec<usize> = header.iter().map(|h| h.chars().count()).collect();
    for row in &rows {
        for (i, cell) in row.iter().enumerate() {
            widths[i] = widths[i].max(cell.chars().count()).min(LIMIT);
        }
    }
    let cells = |row: Vec<String>| row.iter().enumerate().map(|(i, cell)| widgets::fit(cell, widths[i])).collect::<Vec<_>>().join("  ");
    lines.push(Line::from(Span::styled(cells(header.iter().map(|h| h.to_string()).collect()), dim.bg(t.surface).add_modifier(Modifier::BOLD))));
    if rows.is_empty() {
        lines.push(Line::styled("nothing yet", dim));
    }
    lines.extend(rows.into_iter().map(|row| Line::from(cells(row))));
}

impl StatsScreen {
    pub fn new(app: &App) -> StatsScreen {
        let (t, progress, lessons, decks) = (&app.theme, &app.progress, app.lessons, &app.decks);
        let day = today();
        let done = lessons.iter().filter(|l| progress.is_done(l)).count();
        let placed = lessons.iter().filter(|l| progress.is_placed(l)).count();
        let total: usize = lessons.iter().map(|l| l.tasks.len()).sum();
        let solved: usize = lessons.iter().map(|l| progress.best(l).len()).sum();
        let streak = progress.streak();
        let bold = Style::new().add_modifier(Modifier::BOLD);
        let mut lines = vec![Line::from(vec![
            Span::styled(if streak > 0 { format!("{streak}-day") } else { String::new() }, bold),
            Span::raw(if streak > 0 { " streak · " } else { "no streak yet · " }),
            Span::raw(format!("{} trained · ", plural(progress.days_trained().len(), "day"))),
            Span::styled(format!("{done}/{}", lessons.len()), bold),
            Span::raw(format!(" lessons ({placed} placed) · {solved}/{total} tasks solved")),
        ])];
        let rows = progress.efficiency_by_day(7).into_iter().map(|(d, n, keys, reference)| {
            vec![d, n.to_string(), keys.to_string(), reference.to_string(), if keys > 0 { format!("{}%", (100.0 * reference as f64 / keys as f64).round()) } else { String::new() }]
        }).collect();
        table(&mut lines, "Keystrokes · solved tasks · efficiency = reference keys ÷ your keys", &["Day", "Tasks", "Your keys", "Reference", "Efficiency"], rows, t);

        let speed = progress.speed_by_lesson(3);
        let rows = lessons.iter().filter_map(|l| {
            let (n, first, latest, thinking) = speed.get(&l.id)?;
            Some(vec![format!("{} · {}", l.label(), l.title), n.to_string(), format!("{first:.1}s"), format!("{latest:.1}s"), thinking.map_or(String::new(), |s| format!("{s:.1}s"))])
        }).collect();
        table(&mut lines, "Speed · tasks solved from memory, first tries against your latest", &["Lesson", "Timed", "First tries", "Lately", "Before the first key"], rows, t);

        let items = progress.items("card");
        let unlocked: Vec<String> = progress.unlocked(decks, lessons).into_iter().map(|c| c.id).collect();
        let mut rows: Vec<Vec<String>> = decks.values().map(|deck| {
            let seen: Vec<_> = deck.cards.iter().filter_map(|c| items.get(&c.id)).collect();
            vec![deck.title.clone(), deck.cards.len().to_string(), deck.cards.iter().filter(|c| unlocked.contains(&c.id)).count().to_string(), seen.len().to_string(),
                 seen.iter().filter(|i| i.interval >= 21.0).count().to_string(), seen.iter().filter(|i| i.due <= Some(day)).count().to_string()]
        }).collect();
        let drill_items = progress.items("drill");
        let seen: Vec<_> = app.drills.iter().filter_map(|d| drill_items.get(&d.item_id())).collect();
        if hyprland::available() || !seen.is_empty() {
            rows.push(vec!["Omarchy drills (live)".into(), app.drills.len().to_string(), app.drills.len().to_string(), seen.len().to_string(),
                           seen.iter().filter(|i| i.interval >= 21.0).count().to_string(), seen.iter().filter(|i| i.due <= Some(day)).count().to_string()]);
        }
        table(&mut lines, "Decks", &["Deck", "Cards", "Unlocked", "Seen", "Mature (3+ weeks)", "Due today"], rows, t);

        let rows = progress.card_accuracy(7).into_iter().map(|(d, n, correct)| vec![d, n.to_string(), format!("{}%", (100.0 * correct as f64 / n as f64).round())]).collect();
        table(&mut lines, "Card accuracy", &["Day", "Cards answered", "Correct"], rows, t);

        let cards: Vec<_> = decks.values().flat_map(|d| &d.cards).collect();
        let rows = progress.hardest(6).into_iter().filter_map(|item| {
            if let Some(card) = cards.iter().find(|c| c.id == item.id) {
                return Some(vec![card.prompt.clone(), card.shown(), item.lapses.to_string()]);
            }
            let task = lessons.iter().flat_map(|l| &l.tasks).find(|t| t.item_id() == item.id)?;
            Some(vec![task.goal.clone(), task.solution.clone(), item.lapses.to_string()])
        }).collect();
        table(&mut lines, "Trouble spots · forgotten most often", &["What", "Answer", "Forgotten"], rows, t);

        let rows = habits::habits(14).into_iter().take(10).map(|h| vec![h.message, h.recent.to_string(), h.total.to_string(), h.last.to_string()]).collect();
        table(&mut lines, "Habits · what hardtime.nvim caught you doing", &["Message", "Last two weeks", "All time", "Last seen"], rows, t);

        let rows = progress.vimgolf_history(10).into_iter().map(|(d, title, score, best)| {
            vec![d, title, score.map_or("not solved".to_string(), |s| s.to_string()), best.map_or(String::new(), |b| b.to_string())]
        }).collect();
        table(&mut lines, "VimGolf · your score includes ZZ, like on vimgolf.com", &["Day", "Challenge", "Your score", "Best on vimgolf.com"], rows, t);
        StatsScreen { lines, scroll: 0 }
    }

    pub fn key(&mut self, key: KeyEvent) -> Flow {
        match key.code {
            KeyCode::Esc | KeyCode::Char('q') => return Flow::Close,
            KeyCode::Char('j') | KeyCode::Down => self.scroll = (self.scroll + 2).min(self.lines.len() as u16),
            KeyCode::Char('k') | KeyCode::Up => self.scroll = self.scroll.saturating_sub(2),
            _ => {}
        }
        Flow::Stay
    }

    pub fn draw(&self, frame: &mut Frame, app: &App) {
        let [space, bar] = Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).areas(frame.area());
        let block = widgets::pane("Stats", true, &app.theme).padding(Padding::horizontal(2));
        frame.render_widget(Paragraph::new(self.lines.clone()).scroll((self.scroll, 0)).block(block), space);
        frame.render_widget(Paragraph::new(widgets::keybar(&[("j/k", "scroll"), ("esc", "back")], &app.theme)), bar);
    }
}
