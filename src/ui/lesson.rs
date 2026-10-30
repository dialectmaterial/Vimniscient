//! A lesson's intro, and how it went.

use super::app::{App, Flow, Job};
use super::theme::Theme;
use super::text::{RETRY_HELP, ROUNDS_HELP, TASK_HELP, VIMGOLF_HELP, lesson_markdown};
use super::{markdown, widgets};
use crate::core::diagnose::{diagnose, results_summary};
use crate::core::lessons::Lesson;
use crate::core::mnemonics::hooks;
use crate::core::results::TaskResult;
use crossterm::event::{KeyCode, KeyEvent};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Paragraph, Wrap};

const COLUMN: u16 = 76;
const RESULTS: u16 = 96;

fn title(lesson: &Lesson) -> String {
    if lesson.week > 0 { format!("{} · {}", lesson.label(), lesson.title) } else { lesson.title.clone() }
}

/// A lesson's intro; Enter runs it in Neovim.
pub struct Intro {
    title: String,
    lines: Vec<Line<'static>>,
    job: Job,
    scroll: u16,
}

impl Intro {
    pub fn new(lesson: Lesson, job: Job, app: &App) -> Intro {
        let rounds = if lesson.week > 0 {
            format!(" {ROUNDS_HELP} {RETRY_HELP}")
        } else if lesson.id == "review" {
            format!(" {RETRY_HELP}")
        } else {
            String::new()
        };
        let count = if lesson.tasks.len() > 1 { format!("{}.{rounds} ", crate::core::today::plural(lesson.tasks.len(), "task")) } else { String::new() };
        let help = if lesson.id == "vimgolf" { VIMGOLF_HELP } else { TASK_HELP };
        let body = format!("{}\n\n{count}{help}", lesson_markdown(&lesson, None));
        Intro { title: title(&lesson), lines: markdown::render(&body, &app.theme), job, scroll: 0 }
    }

    pub fn key(&mut self, app: &mut App, key: KeyEvent) -> Flow {
        match key.code {
            KeyCode::Enter => {
                app.pending = Some(self.job.clone());
                Flow::Close
            }
            KeyCode::Esc | KeyCode::Char('h') => Flow::Close,
            KeyCode::Char('j') | KeyCode::Down => {
                self.scroll += 2;
                Flow::Stay
            }
            KeyCode::Char('k') | KeyCode::Up => {
                self.scroll = self.scroll.saturating_sub(2);
                Flow::Stay
            }
            _ => Flow::Stay,
        }
    }

    pub fn draw(&self, frame: &mut Frame, app: &App) {
        draw_column(frame, app, COLUMN, &self.title, "", &self.lines, self.scroll, &[("enter", "start"), ("esc", "back")]);
    }
}

fn draw_column(frame: &mut Frame, app: &App, width: u16, title: &str, subtitle: &str, lines: &[Line<'static>], scroll: u16, keys: &[(&str, &str)]) {
    let t = &app.theme;
    let [space, bar] = Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).areas(frame.area());
    let inner_width = width.min(space.width).saturating_sub(6);
    let area: Rect = widgets::centred(space, width, widgets::wrapped_height(lines, inner_width) + 4);
    let mut block = widgets::column(title, t);
    if !subtitle.is_empty() {
        block = widgets::caption(block, subtitle, true, t);
    }
    frame.render_widget(Paragraph::new(lines.to_vec()).wrap(Wrap { trim: false }).scroll((scroll, 0)).block(block), area);
    frame.render_widget(Paragraph::new(widgets::keybar(keys, t)), bar);
}

fn status(status: &str, t: &Theme) -> (&'static str, Color) {
    match status {
        "solved" => ("solved", t.success),
        "failed" => ("missed", t.error),
        "skipped" => ("skipped", t.warning),
        "quit" => ("quit", t.error),
        _ => ("not reached", t.muted),
    }
}

/// For the tasks you missed: the reference keys and what they stand for.
fn why_these_keys(missed: &[&TaskResult], t: &Theme) -> Vec<Line<'static>> {
    let (mut lines, mut said, mut seen): (Vec<Line>, Vec<String>, Vec<&str>) = (Vec::new(), Vec::new(), Vec::new());
    for r in missed {
        if seen.contains(&r.task.solution.as_str()) {
            continue;
        }
        seen.push(&r.task.solution);
        let found: Vec<String> = hooks(&r.task.solution).into_iter().filter(|h| !said.contains(h)).collect();
        if found.is_empty() || lines.len() == 3 {
            continue;
        }
        said.extend(found.iter().cloned());
        lines.push(Line::from(vec![
            Span::styled(format!("{}  ", r.task.solution), Style::new().add_modifier(Modifier::BOLD)),
            Span::styled(found.join(" · "), Style::new().fg(t.accent)),
        ]));
    }
    if !lines.is_empty() {
        lines.insert(0, Line::styled("Why these keys", Style::new().fg(t.muted)));
    }
    lines
}

/// What your own keys said, once each: nothing when there's nothing clear to say.
fn your_keys(results: &[TaskResult], t: &Theme) -> Vec<Line<'static>> {
    let mut said: Vec<String> = Vec::new();
    for r in results.iter().filter(|r| r.status == "solved" && r.task.phase != "learn") {
        let text = diagnose(&r.keys, r.count, r.task.reference());
        if !text.is_empty() && !said.contains(&text) && said.len() < 3 {
            said.push(text);
        }
    }
    if said.is_empty() {
        return Vec::new();
    }
    let mut lines = vec![Line::styled("Your keys", Style::new().fg(t.muted))];
    lines.extend(said.into_iter().map(|text| Line::styled(text, Style::new().fg(t.accent))));
    lines
}

fn row(r: &TaskResult, widths: (usize, usize), t: &Theme) -> Line<'static> {
    let (label, color) = status(&r.status, t);
    let mark = match r.status.as_str() {
        "solved" => "✓",
        "unseen" => "·",
        _ => "✗",
    };
    let limit = r.budget.unwrap_or_else(|| r.task.reference());
    let dim = Style::new().fg(t.muted);
    let (typed, count): (Vec<Span<'static>>, Span<'static>) = match r.status.as_str() {
        "solved" => {
            let good = r.count <= limit;
            (vec![Span::raw(widgets::fit(&r.keys, widths.1))], Span::styled(format!("{:>6}", format!("{}/{limit}", r.count)), Style::new().fg(if good { t.success } else { t.muted })))
        }
        "unseen" => (vec![Span::styled(widgets::fit(label, widths.1), dim)], Span::raw("      ")),
        _ => {
            // what it should have been, louder
            let room = widths.1.saturating_sub(label.chars().count() + 2);
            (vec![Span::styled(format!("{label}  "), dim), Span::styled(widgets::fit(&r.task.solution, room), Style::new().fg(t.accent))], Span::styled(format!("{limit:>6}"), dim))
        }
    };
    let goal = if r.task.phase == "climb" { format!("level {} · {}", r.level, r.task.goal) } else { r.task.goal.clone() };
    let seconds = r.seconds.filter(|_| r.status != "unseen").map_or(String::new(), |s| format!("{s:.1}s"));
    let mut spans = vec![Span::styled(format!("{mark} "), Style::new().fg(color)), Span::raw(format!("{} ", widgets::fit(&goal, widths.0)))];
    spans.extend(typed);
    spans.push(Span::raw(" "));
    spans.push(count);
    spans.push(Span::styled(format!(" {seconds:>6}"), dim));
    Line::from(spans)
}

/// How a lesson went, in the same centred column as cards and the lesson itself.
pub struct Results {
    title: String,
    subtitle: String,
    lines: Vec<Line<'static>>,
    pub job: Option<Job>,
    scroll: u16,
}

impl Results {
    pub fn new(lesson: &Lesson, results: Vec<TaskResult>, note: String, subtitle: String, job: Option<Job>, app: &App) -> Results {
        let t = &app.theme;
        let recall: Vec<&TaskResult> = results.iter().filter(|r| r.task.phase != "learn").collect();
        let two_rounds = recall.len() < results.len();
        let solved = recall.iter().filter(|r| r.status == "solved").count();
        let subtitle = if subtitle.is_empty() { format!("{solved}/{} {}", recall.len(), if two_rounds { "recalled" } else { "solved" }) } else { subtitle };
        let dim = Style::new().fg(t.muted);
        let mut lines = vec![
            widgets::progress_bar(solved, recall.len(), t),
            Line::default(),
            Line::styled(results_summary(&results), Style::new().fg(t.primary).add_modifier(Modifier::BOLD)),
            Line::default(),
        ];
        for line in note.lines() {
            lines.push(Line::styled(line.to_string(), Style::new().fg(t.success)));
        }
        if !note.is_empty() {
            lines.push(Line::default());
        }
        let budgets = results.iter().any(|r| r.budget.is_some());
        let widths = (41, 32); // task, you typed; 90 columns inside the frame
        lines.push(Line::styled(format!("  {} {} {:>6} {:>6}", widgets::fit("task", widths.0), widgets::fit("you typed", widths.1), if budgets { "budget" } else { "ref" }, "time"), dim));
        if two_rounds {
            lines.push(Line::styled("Recall", dim.add_modifier(Modifier::BOLD)));
            lines.extend(recall.iter().map(|r| row(r, widths, t)));
            let learn: Vec<&TaskResult> = results.iter().filter(|r| r.task.phase == "learn").collect();
            lines.push(Line::default());
            let typed = learn.iter().filter(|r| r.status == "solved").count();
            lines.push(Line::styled(format!("Learn · {typed}/{} typed with the keys shown", learn.len()), dim.add_modifier(Modifier::BOLD)));
            lines.extend(learn.iter().map(|r| row(r, widths, t)));
        } else {
            lines.extend(results.iter().map(|r| row(r, widths, t)));
        }
        lines.push(Line::default());
        lines.push(Line::styled(if budgets { "n/budget: your keys and the most allowed at that level" } else { "n/ref: your keys and the reference solution's; fewer and you beat it" }, dim));
        lines.push(Line::styled("time: from the task appearing to it ending; just for you, nothing is graded on it", dim));
        let missed: Vec<&TaskResult> = results.iter().filter(|r| matches!(r.status.as_str(), "failed" | "skipped")).collect();
        for block in [why_these_keys(&missed, t), your_keys(&results, t)] {
            if !block.is_empty() {
                lines.push(Line::default());
                lines.extend(block);
            }
        }
        Results { title: title(lesson), subtitle, lines, job, scroll: 0 }
    }

    pub fn key(&mut self, app: &mut App, key: KeyEvent) -> Flow {
        match key.code {
            KeyCode::Char('r') => {
                app.pending = self.job.clone();
                Flow::Close
            }
            KeyCode::Esc | KeyCode::Enter | KeyCode::Char('q') => Flow::Close,
            KeyCode::Char('j') | KeyCode::Down => {
                self.scroll += 2;
                Flow::Stay
            }
            KeyCode::Char('k') | KeyCode::Up => {
                self.scroll = self.scroll.saturating_sub(2);
                Flow::Stay
            }
            _ => Flow::Stay,
        }
    }

    pub fn draw(&self, frame: &mut Frame, app: &App) {
        draw_column(frame, app, RESULTS, &self.title, &self.subtitle, &self.lines, self.scroll, &[("enter", "done"), ("r", "again")]);
    }
}
