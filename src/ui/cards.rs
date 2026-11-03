//! The card screen: type the keys for each prompt.

use super::app::{App, Flow};
use super::input::Input;
use super::theme::Theme;
use super::widgets;
use crate::core::card_session::CardSession;
use crate::core::cards::Card;
use crate::core::mnemonics::hooks;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Paragraph, Wrap};

// decks whose answers are Vim keys, so hooks() can say what they stand for
const HOOK_DECKS: [&str; 3] = ["vim", "lazyvim", "habits"];

pub struct CardScreen {
    pub session: Option<CardSession>,
    cards: Vec<Card>,
    title: String,
    pub input: Input,
    copy_again: bool,
    started: bool,
}

fn why(card: &Card) -> Vec<String> {
    if HOOK_DECKS.contains(&card.deck.as_str()) { hooks(&card.answers[0]) } else { Vec::new() }
}

impl CardScreen {
    pub fn new(cards: Vec<Card>, title: &str) -> CardScreen {
        CardScreen { session: None, cards, title: title.into(), input: Input::default(), copy_again: false, started: false }
    }

    fn start(&mut self, app: &App) {
        if !self.started {
            self.started = true;
            let mut session = CardSession::new(std::mem::take(&mut self.cards));
            session.begin(&app.progress);
            self.session = Some(session);
        }
    }

    /// A new card's answer, to type once; it's asked from memory next time.
    fn introduction(&self, card: &Card, t: &Theme) -> Vec<Line<'static>> {
        let lead = if self.copy_again {
            vec![Span::styled("✗", Style::new().fg(t.error)), Span::raw("  type it as shown: ")]
        } else {
            vec![Span::styled("new", Style::new().fg(t.accent)), Span::raw("  type it once: ")]
        };
        let mut first = lead;
        first.push(Span::styled(card.shown(), Style::new().add_modifier(Modifier::BOLD)));
        let dim = Style::new().fg(t.muted);
        let mut lines = vec![Line::from(first)];
        if !card.note.is_empty() {
            lines.push(Line::styled(card.note.clone(), dim));
        }
        lines.extend(why(card).into_iter().map(|h| Line::styled(h, dim)));
        lines
    }

    fn feedback(card: &Card, correct: bool, t: &Theme) -> Vec<Line<'static>> {
        let mut first = vec![
            Span::styled(if correct { "✓" } else { "✗" }, Style::new().fg(if correct { t.success } else { t.error })),
            Span::raw("  "),
            Span::styled(card.shown(), Style::new().add_modifier(Modifier::BOLD)),
        ];
        let dim = Style::new().fg(t.muted);
        if card.answers.len() > 1 {
            let also: Vec<String> = card.answers[1..].iter().map(|a| crate::core::answer::display_keys(a)).collect();
            first.push(Span::styled(format!("   also {}", also.join(", ")), dim));
        }
        let mut lines = vec![Line::from(first)];
        if !card.note.is_empty() {
            lines.push(Line::styled(card.note.clone(), dim));
        }
        // what the keys stand for, only now that the answer is out; louder after a miss
        let style = if correct { dim } else { Style::new().fg(t.accent) };
        lines.extend(why(card).into_iter().map(|h| Line::styled(h, style)));
        lines
    }

    pub fn key(&mut self, app: &mut App, key: KeyEvent) -> Flow {
        self.start(app);
        let Some(session) = &mut self.session else { return Flow::Close };
        if key.code == KeyCode::Esc {
            session.settle(&app.progress);
            return Flow::Close;
        }
        if session.pending.is_some() {
            match key.code {
                KeyCode::Enter => {
                    session.settle(&app.progress);
                    self.input.clear();
                    self.copy_again = false;
                    if session.begin(&app.progress).is_none() {
                        return Flow::Close;
                    }
                }
                KeyCode::Char('o') if session.pending.as_ref().is_some_and(|p| !p.1) => session.accept(),
                _ => {}
            }
            return Flow::Stay;
        }
        if key.code == KeyCode::Enter {
            if !session.submit(&self.input.value()) {
                self.input.clear(); // copying it out: try again
                self.copy_again = true;
            }
        } else if let Some(text) = session.card().and_then(|card| pressed(card, &self.input, key)) {
            self.input.insert(&text);
        } else {
            self.input.key(key);
        }
        Flow::Stay
    }

    pub fn draw(&self, frame: &mut Frame, app: &App) {
        let t = &app.theme;
        // the session starts on the first key; before that the first card is still at hand
        let (card, done, total, intro, pending) = match &self.session {
            Some(s) => (s.card().cloned(), s.done(), s.total, s.intro, s.pending.clone()),
            None => {
                let card = self.cards.first().cloned();
                let intro = card.as_ref().is_some_and(|c| !app.progress.ever_right(&c.id) && app.progress.item(&c.id).is_none_or(|i| i.reps == 0));
                (card, 0, self.cards.len(), intro, None)
            }
        };
        let Some(card) = card else { return };
        let retried = self.session.as_ref().is_some_and(|s| s.retried.contains(&card.id));
        let tag = if intro { "new · " } else if retried { "again · " } else { "" };
        let subtitle = format!("{tag}{}/{total}", (done + 1).min(total));
        let deck = app.decks.get(&card.deck).map_or("", |d| d.title.as_str());
        let [space, bar] = Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).areas(frame.area());
        let width = 76.min(space.width);
        let inner = width.saturating_sub(6);
        let prompt = Line::styled(card.prompt.clone(), Style::new().fg(t.primary).add_modifier(Modifier::BOLD));
        let feedback = match &pending {
            Some((shown, correct, _)) => Self::feedback(shown, *correct, t),
            None if intro => self.introduction(&card, t),
            None => Vec::new(),
        };
        let prompt_rows = widgets::wrapped_height(std::slice::from_ref(&prompt), inner);
        let feedback_rows = widgets::wrapped_height(&feedback, inner).max(3);
        let area = widgets::centred(space, width, prompt_rows + feedback_rows + 12);
        let block = widgets::caption(widgets::column(&format!("{} · {deck}", self.title), t), &subtitle, true, t);
        let inside = block.inner(area);
        frame.render_widget(block, area);
        let [line, _, words, _, input, _, below] = Layout::vertical([Constraint::Length(1), Constraint::Length(1), Constraint::Length(prompt_rows), Constraint::Length(1), Constraint::Length(3), Constraint::Length(1), Constraint::Min(0)]).areas(inside);
        frame.render_widget(Paragraph::new(widgets::progress_bar(done, total, t)), line);
        frame.render_widget(Paragraph::new(prompt).wrap(Wrap { trim: false }), words);
        let typing = pending.is_none();
        let shown = if self.input.chars.is_empty() && typing {
            let hint = if card.deck == "tmux" {
                "modifiers + key, like CTRL SHIFT + X; press Ctrl-Space for the prefix"
            } else if card.style == "combo" {
                "modifiers + key, like CTRL SHIFT + X"
            } else {
                "the keys as typed: press Space for the leader, <C-x> for Ctrl-x"
            };
            Line::styled(hint, Style::new().fg(t.muted))
        } else {
            Line::from(self.input.value())
        };
        frame.render_widget(Paragraph::new(shown).block(widgets::plain(typing, t).padding(ratatui::widgets::Padding::horizontal(1))), input);
        if typing {
            frame.set_cursor_position((input.x + 2 + self.input.cursor as u16, input.y + 1));
        }
        frame.render_widget(Paragraph::new(feedback).wrap(Wrap { trim: false }), below);
        let keys: &[(&str, &str)] = match &pending {
            Some((_, false, _)) => &[("enter", "next"), ("o", "I was right"), ("esc", "stop")],
            Some(_) => &[("enter", "next"), ("esc", "stop")],
            None => &[("enter", "check"), ("esc", "stop")],
        };
        frame.render_widget(Paragraph::new(widgets::keybar(keys, t)), bar);
    }
}

/// Keys that stand for more than a character: Space at the start is the leader,
/// Ctrl-Space or Ctrl-B in a tmux card the prefix. Typed out the way they're shown.
fn pressed(card: &Card, input: &Input, key: KeyEvent) -> Option<String> {
    let control = key.modifiers.contains(KeyModifiers::CONTROL);
    let at_end = input.cursor == input.chars.len();
    if card.style == "keys" && key.code == KeyCode::Char(' ') && !control && at_end {
        // only leaders so far: "Space Space " for <leader><Space>
        let value = input.value();
        let leaders = value.split_whitespace().all(|word| word == "Space") && (value.is_empty() || value.ends_with(' '));
        return leaders.then(|| "Space ".to_string());
    }
    if card.deck == "tmux" && card.style == "combo" {
        let chord = match key.code {
            // terminals send Ctrl-Space as NUL
            KeyCode::Null => crate::core::answer::TMUX_PREFIX_KEYS,
            KeyCode::Char(' ') if control => crate::core::answer::TMUX_PREFIX_KEYS,
            KeyCode::Char('b') if control => "CTRL + B",
            _ => return None,
        };
        // the prefix comes first and a key follows it; the prefix card itself wants just the chord
        let then = input.chars.is_empty() && card.answers.iter().any(|a| a.starts_with("PREFIX"));
        return Some(if then { format!("{chord}, ") } else { chord.to_string() });
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn card(deck: &str, style: &str, answers: &[&str]) -> Card {
        Card { deck: deck.into(), style: style.into(), answers: answers.iter().map(|a| a.to_string()).collect(), ..Card::default() }
    }

    /// Types `keys` into a fresh box the way the card screen does.
    fn typed(card: &Card, keys: &[KeyEvent]) -> String {
        let mut input = Input::default();
        for &key in keys {
            match pressed(card, &input, key) {
                Some(text) => input.insert(&text),
                None => input.key(key),
            }
        }
        input.value()
    }

    fn plain(c: char) -> KeyEvent {
        KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE)
    }

    fn ctrl(c: char) -> KeyEvent {
        KeyEvent::new(KeyCode::Char(c), KeyModifiers::CONTROL)
    }

    #[test]
    fn space_types_the_leader() {
        let lazy = card("lazyvim", "keys", &["<leader>ff"]);
        let got = typed(&lazy, &[plain(' '), plain('f'), plain('f')]);
        assert_eq!(got, "Space ff");
        assert!(crate::core::answer::is_correct(&got, &lazy.answers, "keys", true));
        let twice = card("lazyvim", "keys", &["<leader><Space>"]);
        let got = typed(&twice, &[plain(' '), plain(' ')]);
        assert!(crate::core::answer::is_correct(&got, &twice.answers, "keys", true), "{got:?}");
        // later spaces are just spaces
        assert_eq!(typed(&lazy, &[plain(':'), plain('w'), plain(' '), plain('x')]), ":w x");
    }

    #[test]
    fn ctrl_space_or_b_types_the_tmux_prefix() {
        let window = card("tmux", "combo", &["PREFIX + c"]);
        for prefix in [ctrl(' '), ctrl('b'), KeyEvent::new(KeyCode::Null, KeyModifiers::NONE)] {
            let got = typed(&window, &[prefix, plain('c')]);
            assert!(crate::core::answer::is_correct(&got, &window.answers, "combo", true), "{got:?}");
        }
        let send = card("tmux", "combo", &["PREFIX + CTRL + SPACE"]);
        let got = typed(&send, &[ctrl(' '), ctrl(' ')]);
        assert!(crate::core::answer::is_correct(&got, &send.answers, "combo", true), "{got:?}");
        let prefix = card("tmux", "combo", &["CTRL + SPACE", "CTRL + B"]);
        assert_eq!(typed(&prefix, &[ctrl('b')]), "CTRL + B");
        assert!(crate::core::answer::is_correct(&typed(&prefix, &[ctrl(' ')]), &prefix.answers, "combo", true));
        // other decks keep Ctrl-B to themselves
        assert_eq!(typed(&card("omarchy", "combo", &["SUPER + B"]), &[ctrl('b')]), "");
    }
}
