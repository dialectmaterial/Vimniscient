//! Pieces every screen uses: panes, key bars, progress bars, small text helpers.

use super::theme::Theme;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Padding};

/// A rounded pane with its title set into the border, lazygit-style.
pub fn pane<'a>(title: &str, focused: bool, t: &Theme) -> Block<'a> {
    let border = if focused { t.primary } else { t.panel };
    let color = if focused { t.primary } else { t.muted };
    Block::bordered().border_type(BorderType::Rounded).border_style(Style::new().fg(border)).style(Style::new().bg(t.background).fg(t.foreground))
        .title(Line::from(vec![Span::styled("─ ", Style::new().fg(border)), Span::styled(format!("{title} "), Style::new().fg(color))]))
}

/// A rounded box with no title.
pub fn plain<'a>(focused: bool, t: &Theme) -> Block<'a> {
    Block::bordered().border_type(BorderType::Rounded).border_style(Style::new().fg(if focused { t.primary } else { t.panel })).style(Style::new().bg(t.background).fg(t.foreground))
}

/// A pane's right-hand caption along the bottom border.
pub fn caption<'a>(block: Block<'a>, text: &str, focused: bool, t: &Theme) -> Block<'a> {
    let border = if focused { t.primary } else { t.panel };
    block.title_bottom(Line::from(vec![Span::styled(format!(" {text} "), Style::new().fg(t.muted)), Span::styled("─", Style::new().fg(border))]).right_aligned())
}

/// A centred column's frame: always in the primary colour, with room inside.
pub fn column<'a>(title: &str, t: &Theme) -> Block<'a> {
    pane(title, true, t).padding(Padding::new(2, 2, 1, 1))
}

/// One line of key hints: the key in the primary colour, what it does after it.
pub fn keybar(pairs: &[(&str, &str)], t: &Theme) -> Line<'static> {
    let mut spans = vec![Span::raw(" ")];
    for (i, (key, what)) in pairs.iter().enumerate() {
        if i > 0 {
            spans.push(Span::raw("  "));
        }
        spans.push(Span::styled(key.to_string(), Style::new().fg(t.primary).add_modifier(Modifier::BOLD)));
        spans.push(Span::styled(format!(" {what}"), Style::new().fg(t.muted)));
    }
    Line::from(spans)
}

pub fn progress_bar(done: usize, total: usize, t: &Theme) -> Line<'static> {
    const WIDTH: usize = 40;
    let filled = if total > 0 { (WIDTH * done + total / 2) / total } else { 0 };
    Line::from(vec![Span::styled("━".repeat(filled), Style::new().fg(t.primary)), Span::styled("━".repeat(WIDTH - filled), Style::new().fg(t.panel))])
}

/// A rectangle `width` by `height`, centred in `area` and no bigger than it (or 90% high).
pub fn centred(area: Rect, width: u16, height: u16) -> Rect {
    let width = width.min(area.width);
    let height = height.min(area.height * 9 / 10);
    Rect::new(area.x + (area.width - width) / 2, area.y + (area.height - height) / 2, width, height)
}

/// How many rows `lines` take when wrapped to `width`.
pub fn wrapped_height(lines: &[Line], width: u16) -> u16 {
    lines.iter().map(|line| (line.width().max(1) as u16).div_ceil(width.max(1))).sum()
}

/// `text` cut or padded to exactly `width` columns.
pub fn fit(text: &str, width: usize) -> String {
    let count = text.chars().count();
    if count > width {
        let mut cut: String = text.chars().take(width.saturating_sub(1)).collect();
        cut.push('…');
        cut
    } else {
        format!("{text}{}", " ".repeat(width - count))
    }
}
