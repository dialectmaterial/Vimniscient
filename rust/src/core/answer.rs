//! Checking typed answers to cards. Two styles: `keys` for key sequences (`ciw`,
//! `<C-a>`, `<leader>ff`) and `combo` for chords (`SUPER SHIFT + B`). Both accept
//! the usual ways of writing the same thing.

use fancy_regex::{Captures, Regex};
use std::collections::BTreeSet;
use std::sync::LazyLock;

const LEADER: &str = "\u{0}";

macro_rules! regex {
    ($name:ident, $pattern:expr) => {
        static $name: LazyLock<Regex> = LazyLock::new(|| Regex::new($pattern).expect("a valid pattern"));
    };
}

regex!(LEADING, r"(?i)^(leader|space|spc)(\s*\+\s*|\s+|$)");
regex!(SPACE, r"(?i)(?<![<\w])space(?![>\w])");
regex!(CTRL, r"(?i)\b(?:ctrl|control)[-+ ]+(\S)");
regex!(ALT, r"(?i)\b(?:alt|meta)[-+ ]+(\S)");
regex!(CARET, r"\^([A-Za-z_\[\]])");
regex!(TOKEN, r"<([^<>\s]+)>");
regex!(MODIFIED, r"(?i)^([csma])-(.+)$");
regex!(FUNCTION, r"^f\d+$");
regex!(GAPS, r"\s+");
regex!(COPY_MODE, r"(?i)copy\s+mode");
regex!(PAGE, r"(?i)page\s+(up|down)");
regex!(PLUS_KEY, r"[\s+]\+\s*$");
regex!(PLUS_END, r"\+\s*$");
regex!(SPLIT, r"[\s+]+");

fn token_name(low: &str) -> Option<&'static str> {
    Some(match low {
        "esc" | "escape" => "<Esc>",
        "cr" | "enter" | "return" => "<CR>",
        "tab" => "<Tab>",
        "bs" | "backspace" => "<BS>",
        "space" => "<Space>",
        "lt" => "<",
        "bar" => "|",
        "bslash" => "\\",
        "home" => "<Home>",
        "end" => "<End>",
        "del" | "delete" => "<Del>",
        "up" => "<Up>",
        "down" => "<Down>",
        "left" => "<Left>",
        "right" => "<Right>",
        _ => return None,
    })
}

fn norm_token(caps: &Captures) -> String {
    let inner = &caps[1];
    let low = inner.to_lowercase();
    if (low == "leader" || low == "space") && caps.get(0).is_some_and(|m| m.start() == 0) {
        return LEADER.into();
    }
    if let Some(name) = token_name(&low) {
        return name.into();
    }
    if let Ok(Some(m)) = MODIFIED.captures(inner) {
        let modifier = match m[1].to_lowercase().as_str() {
            "c" => "C",
            "s" => "S",
            _ => "M",
        };
        let key = &m[2];
        let key = if modifier == "C" && key.chars().count() == 1 { key.to_lowercase() } else { key.to_string() };
        return format!("<{modifier}-{key}>");
    }
    if FUNCTION.is_match(&low).unwrap_or(false) {
        return format!("<F{}>", &low[1..]);
    }
    format!("<{inner}>")
}

pub fn norm_keys(text: &str, case_sensitive: bool) -> String {
    let s = LEADING.replace_all(text.trim(), "<leader>").into_owned();
    let s = SPACE.replace_all(&s, "<Space>").into_owned();
    let s = CTRL.replace_all(&s, "<C-$1>").into_owned();
    let s = ALT.replace_all(&s, "<M-$1>").into_owned();
    let s = CARET.replace_all(&s, "<C-$1>").into_owned();
    let s = TOKEN.replace_all(&s, |caps: &Captures| norm_token(caps)).into_owned();
    let s = GAPS.replace_all(&s, "").into_owned();
    let s = if s.starts_with(':') { s.strip_suffix("<CR>").unwrap_or(&s).to_string() } else { s };
    if case_sensitive { s } else { s.to_lowercase() }
}

fn modifier(part: &str) -> Option<&'static str> {
    Some(match part {
        "SUPER" | "WIN" | "CMD" | "MOD" | "LOGO" => "SUPER",
        "CTRL" | "CONTROL" | "CTL" => "CTRL",
        "ALT" | "OPT" | "OPTION" | "MOD1" | "META" => "ALT",
        "SHIFT" => "SHIFT",
        "PREFIX" | "LEADER" => "PREFIX",
        "COPYMODE" => "COPYMODE",
        _ => return None,
    })
}

fn key_alias(part: &str) -> Option<&'static str> {
    Some(match part {
        "ENTER" | "CR" => "RETURN",
        "ESC" => "ESCAPE",
        "DEL" => "DELETE",
        "INS" => "INSERT",
        "PGUP" | "PAGEUP" | "PRIOR" => "PAGE_UP",
        "PGDN" | "PAGEDOWN" | "NEXT" => "PAGE_DOWN",
        "=" => "EQUAL",
        "-" => "MINUS",
        "+" => "PLUS",
        "SPACEBAR" => "SPACE",
        "PRTSC" | "PRINTSCREEN" => "PRINT",
        _ => return None,
    })
}

pub fn norm_combo(text: &str, case_sensitive: bool) -> (BTreeSet<&'static str>, Vec<String>) {
    let s = COPY_MODE.replace_all(text.trim(), "COPYMODE").into_owned();
    let mut s = PAGE.replace_all(&s, "PAGE_$1").into_owned();
    let plus_key = PLUS_KEY.is_match(&s).unwrap_or(false); // "CTRL + +" or "CTRL +"
    if plus_key {
        s = PLUS_END.replace_all(&s, "").into_owned();
    }
    let mut parts: Vec<String> = Vec::new();
    for part in SPLIT.split(&s).flatten() {
        if part.chars().count() > 1 && part.contains('-') {
            parts.extend(part.split('-').filter(|p| !p.is_empty()).map(str::to_string));
        } else if !part.is_empty() {
            parts.push(part.to_string());
        }
    }
    if plus_key {
        parts.push("+".into());
    }
    let mut mods = BTreeSet::new();
    let mut keys: Vec<String> = Vec::new();
    for part in parts {
        let upper = part.to_uppercase();
        if let Some(found) = modifier(&upper) {
            mods.insert(found);
            continue;
        }
        let key = key_alias(&upper).map(str::to_string).unwrap_or(part);
        keys.push(if case_sensitive && key.chars().count() == 1 { key } else { key.to_uppercase() });
    }
    // SHIFT + c is C when case matters (tmux)
    if case_sensitive && mods.contains("SHIFT") && keys.len() == 1 && keys[0].chars().count() == 1 && keys[0].chars().all(char::is_alphabetic) {
        mods.remove("SHIFT");
        keys = vec![keys[0].to_uppercase()];
    }
    (mods, keys)
}

pub fn is_correct(answer: &str, expected: &[String], style: &str, case_sensitive: bool) -> bool {
    if answer.trim().is_empty() {
        return false;
    }
    if style == "combo" {
        let got = norm_combo(answer, case_sensitive);
        return expected.iter().any(|e| norm_combo(e, case_sensitive) == got);
    }
    let got = norm_keys(answer, case_sensitive);
    expected.iter().any(|e| norm_keys(e, case_sensitive) == got)
}

/// `<Space>ff` reads better as `<leader>ff`.
pub fn pretty_keys(keys: &str) -> String {
    match keys.strip_prefix("<Space>") {
        Some(rest) => format!("<leader>{rest}"),
        None => keys.to_string(),
    }
}
