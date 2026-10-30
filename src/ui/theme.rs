//! Colours: the Omarchy theme in use, Catppuccin Mocha's own palette by default.

use crate::core::cards::home;
use ratatui::style::Color;
use serde_json::{Value, json};

const fn digit(c: u8) -> u8 {
    match c {
        b'0'..=b'9' => c - b'0',
        b'a'..=b'f' => c - b'a' + 10,
        _ => c - b'A' + 10,
    }
}

const fn rgb(hex: &str) -> Color {
    let b = hex.as_bytes();
    Color::Rgb(digit(b[1]) * 16 + digit(b[2]), digit(b[3]) * 16 + digit(b[4]), digit(b[5]) * 16 + digit(b[6]))
}

#[derive(Clone, Copy, Debug)]
pub struct Theme {
    pub name: &'static str,
    pub background: Color,
    pub foreground: Color,
    pub primary: Color,
    pub secondary: Color,
    pub accent: Color,
    pub success: Color,
    pub warning: Color,
    pub error: Color,
    pub surface: Color,
    pub panel: Color,
    pub muted: Color,
    pub selected: Color,
}

pub const THEMES: [Theme; 7] = [
    Theme { name: "vimniscient-mocha", background: rgb("#1E1E2E"), foreground: rgb("#CDD6F4"), primary: rgb("#CBA6F7"), secondary: rgb("#89B4FA"), accent: rgb("#B4BEFE"), success: rgb("#A6E3A1"), warning: rgb("#F9E2AF"), error: rgb("#F38BA8"), surface: rgb("#313244"), panel: rgb("#45475A"), muted: rgb("#A5A5AB"), selected: rgb("#494060") },
    Theme { name: "vimniscient-latte", background: rgb("#EFF1F5"), foreground: rgb("#4C4F69"), primary: rgb("#8839EF"), secondary: rgb("#1E65F5"), accent: rgb("#7287FD"), success: rgb("#40A02B"), warning: rgb("#DE8E1D"), error: rgb("#D10F39"), surface: rgb("#CCD0DA"), panel: rgb("#BCC0CC"), muted: rgb("#5F6062"), selected: rgb("#D5C3F3") },
    Theme { name: "gruvbox", background: rgb("#282828"), foreground: rgb("#FBF1C7"), primary: rgb("#85A598"), secondary: rgb("#A89A85"), accent: rgb("#F9BD2F"), success: rgb("#B7BB26"), warning: rgb("#FD8019"), error: rgb("#FA4934"), surface: rgb("#3C3836"), panel: rgb("#504945"), muted: rgb("#A9A9A9"), selected: rgb("#3F4744") },
    Theme { name: "nord", background: rgb("#2E3440"), foreground: rgb("#D8DEE9"), primary: rgb("#88C0D0"), secondary: rgb("#81A1C1"), accent: rgb("#B48EAD"), success: rgb("#A3BE8C"), warning: rgb("#EACB8B"), error: rgb("#BE616A"), surface: rgb("#3B4252"), panel: rgb("#434C5E"), muted: rgb("#ABADB2"), selected: rgb("#445764") },
    Theme { name: "tokyo-night", background: rgb("#1A1B26"), foreground: rgb("#A9B1D6"), primary: rgb("#BB9AF7"), secondary: rgb("#7AA2F7"), accent: rgb("#FE9E64"), success: rgb("#9ECE6A"), warning: rgb("#DFAF68"), error: rgb("#F6768E"), surface: rgb("#24283B"), panel: rgb("#414868"), muted: rgb("#A3A3A8"), selected: rgb("#423A5A") },
    Theme { name: "rose-pine", background: rgb("#191724"), foreground: rgb("#E0DEF4"), primary: rgb("#C4A7E7"), secondary: rgb("#31748F"), accent: rgb("#EBBCBA"), success: rgb("#9CCFD8"), warning: rgb("#F5C177"), error: rgb("#EA6F92"), surface: rgb("#1F1D2E"), panel: rgb("#26233A"), muted: rgb("#A3A2A7"), selected: rgb("#433B54") },
    Theme { name: "flexoki", background: rgb("#100F0F"), foreground: rgb("#FFFCF0"), primary: rgb("#205EA6"), secondary: rgb("#24837B"), accent: rgb("#9B76C8"), success: rgb("#65800B"), warning: rgb("#AC8301"), error: rgb("#AE3029"), surface: rgb("#1C1B1A"), panel: rgb("#282726"), muted: rgb("#9F9F9F"), selected: rgb("#142234") },
];

/// The theme of ~/.local/state/omarchy/current/theme.name, when it has a twin here.
pub fn omarchy_theme() -> Theme {
    let state = std::env::var_os("XDG_STATE_HOME").map(std::path::PathBuf::from).unwrap_or_else(|| home().join(".local/state"));
    let name = std::fs::read_to_string(state.join("omarchy/current/theme.name")).unwrap_or_default();
    let wanted = match name.trim().to_lowercase().as_str() {
        "catppuccin-latte" => "vimniscient-latte",
        "gruvbox" => "gruvbox",
        "nord" => "nord",
        "tokyo-night" => "tokyo-night",
        "rose-pine" => "rose-pine",
        "flexoki-light" => "flexoki",
        _ => "vimniscient-mocha",
    };
    *THEMES.iter().find(|t| t.name == wanted).unwrap_or(&THEMES[0])
}

fn hex(color: Color) -> String {
    match color {
        Color::Rgb(r, g, b) => format!("#{r:02x}{g:02x}{b:02x}"),
        _ => "#000000".into(),
    }
}

/// The theme's colours as hex, for lessons in Neovim to draw with.
pub fn lesson_colors(t: &Theme) -> Value {
    json!({"background": hex(t.background), "foreground": hex(t.foreground), "muted": hex(t.muted), "primary": hex(t.primary),
           "accent": hex(t.accent), "success": hex(t.success), "error": hex(t.error), "panel": hex(t.panel)})
}
