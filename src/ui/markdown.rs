//! The little Markdown lesson intros use: paragraphs, lists, bold, italics, code, links.

use super::theme::Theme;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};

fn inline(text: &str, t: &Theme) -> Vec<Span<'static>> {
    let chars: Vec<char> = text.chars().collect();
    let plain = Style::new().fg(t.foreground);
    let (mut spans, mut buffer, mut i) = (Vec::new(), String::new(), 0);
    let mut bold = false;
    let mut italic = false;
    let style = |bold: bool, italic: bool| {
        let mut s = plain;
        if bold { s = s.add_modifier(Modifier::BOLD); }
        if italic { s = s.add_modifier(Modifier::ITALIC); }
        s
    };
    while i < chars.len() {
        let c = chars[i];
        if c == '`' {
            let run = chars[i..].iter().take_while(|&&x| x == '`').count();
            let close = (i + run..chars.len()).find(|&j| chars[j..].iter().take_while(|&&x| x == '`').count() == run && (j == 0 || chars[j - 1] != '`'));
            if let Some(end) = close {
                if !buffer.is_empty() {
                    spans.push(Span::styled(std::mem::take(&mut buffer), style(bold, italic)));
                }
                let code: String = chars[i + run..end].iter().collect();
                let code = if run > 1 { code.trim().to_string() } else { code };
                spans.push(Span::styled(code, Style::new().fg(t.primary).bg(t.surface)));
                i = end + run;
                continue;
            }
        }
        if c == '*' {
            if !buffer.is_empty() {
                spans.push(Span::styled(std::mem::take(&mut buffer), style(bold, italic)));
            }
            if chars.get(i + 1) == Some(&'*') {
                bold = !bold;
                i += 2;
            } else {
                italic = !italic;
                i += 1;
            }
            continue;
        }
        if c == '[' && let Some(close) = chars[i..].iter().position(|&x| x == ']')
            && chars.get(i + close + 1) == Some(&'(')
            && let Some(end) = chars[i + close..].iter().position(|&x| x == ')')
        {
            buffer.extend(&chars[i + 1..i + close]);
            i += close + end + 1;
            continue;
        }
        buffer.push(c);
        i += 1;
    }
    if !buffer.is_empty() {
        spans.push(Span::styled(buffer, style(bold, italic)));
    }
    spans
}

pub fn render(text: &str, t: &Theme) -> Vec<Line<'static>> {
    let mut lines = Vec::new();
    for block in text.split("\n\n").filter(|b| !b.trim().is_empty()) {
        if !lines.is_empty() {
            lines.push(Line::default());
        }
        if block.lines().all(|l| l.starts_with("- ")) {
            for item in block.lines() {
                let mut spans = vec![Span::styled(" • ", Style::new().fg(t.primary))];
                spans.extend(inline(&item[2..], t));
                lines.push(Line::from(spans));
            }
        } else {
            let joined: Vec<&str> = block.lines().map(str::trim).collect();
            lines.push(Line::from(inline(&joined.join(" "), t)));
        }
    }
    lines
}
