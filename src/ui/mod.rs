//! The terminal interface. Laid out like lazygit: everything on one screen in titled
//! panes, Tab moves focus, one key bar at the bottom, nothing animates. Cards and drills
//! get a centred focus screen. Colours come from the Omarchy theme in use.

pub mod app;
mod cards;
mod drills;
mod input;
mod lesson;
mod main_screen;
mod markdown;
mod quick;
mod stats;
mod text;
pub mod theme;
mod widgets;

use crate::system::nvim::mouse_wheel;
use crate::system::vimgolf::Challenge;
use app::App;
use crossterm::event::{self, Event, KeyEventKind};
use std::time::Duration;

/// Lessons draw in the Omarchy theme's colours, from the menu or the command line.
pub fn use_theme() {
    if let Ok(mut colors) = crate::system::nvim::COLORS.lock() {
        *colors = Some(theme::lesson_colors(&theme::omarchy_theme()));
    }
}

/// What arrives from other threads.
pub enum Message {
    Hyprland(String),
    Golf(Result<Option<Challenge>, String>),
}

pub fn run() {
    let mut app = App::new();
    use_theme();
    let mut terminal = ratatui::init();
    mouse_wheel(false); // keyboard only: nothing here reacts to clicks or the wheel
    while !app.quit {
        if terminal.draw(|frame| app.draw(frame)).is_err() {
            break;
        }
        if let Some(job) = app.pending.take() {
            ratatui::restore();
            app.execute(job);
            terminal = ratatui::init();
            mouse_wheel(false);
            let _ = terminal.clear();
            continue;
        }
        if event::poll(Duration::from_millis(100)).unwrap_or(false) {
            match event::read() {
                Ok(Event::Key(key)) if key.kind != KeyEventKind::Release => app.press(key),
                _ => {}
            }
        }
        app.tick();
    }
    ratatui::restore();
    mouse_wheel(true);
    app.leave();
}
