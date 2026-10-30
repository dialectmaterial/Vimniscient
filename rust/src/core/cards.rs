//! Flashcard decks. The static ones come from `cards/*.yaml`; a deck about a
//! program only shows up when that program is installed.

use super::{answer::pretty_keys, content, habits};
use fancy_regex::Regex;
use indexmap::IndexMap;
use serde_norway::Value;
use std::collections::HashSet;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::LazyLock;
use std::time::{Duration, Instant};

// New cards are introduced round-robin in this order.
pub const DECK_ORDER: [&str; 8] = ["habits", "vim", "lazyvim", "omarchy", "tmux", "shell", "foot", "zathura"];

#[derive(Clone, Debug, Default)]
pub struct Card {
    pub deck: String,
    pub id: String,
    pub prompt: String,
    pub answers: Vec<String>,
    pub style: String, // keys | combo
    pub case_sensitive: bool,
    pub week: u32,
    pub day: u32, // the lesson (in `week`) that teaches it; 0 for none
    pub note: String,
    pub order: usize, // position within the deck for introducing new cards
}

impl Card {
    pub fn shown(&self) -> String {
        pretty_keys(&self.answers[0])
    }
}

#[derive(Clone, Debug, Default)]
pub struct Deck {
    pub id: String,
    pub title: String,
    pub cards: Vec<Card>,
}

pub fn nvim_data() -> PathBuf {
    std::env::var_os("XDG_DATA_HOME").map(PathBuf::from).unwrap_or_else(|| home().join(".local/share")).join("nvim")
}

pub fn home() -> PathBuf {
    std::env::var_os("HOME").map(PathBuf::from).unwrap_or_default()
}

/// A Neovim plugin installed through lazy.nvim.
pub fn has_plugin(name: &str) -> bool {
    nvim_data().join("lazy").join(name).is_dir()
}

/// LazyVim's lessons and cards need it.
pub fn has_lazyvim() -> bool {
    has_plugin("LazyVim")
}

pub fn on_path(program: &str) -> bool {
    std::env::var_os("PATH").is_some_and(|path| std::env::split_paths(&path).any(|dir| dir.join(program).is_file()))
}

fn static_decks() -> IndexMap<String, Deck> {
    let mut decks = IndexMap::new();
    for name in content::names("cards") {
        let data: Value = serde_norway::from_str(&content::text(&name)).unwrap_or_else(|e| panic!("{name}: {e}"));
        // a deck about a program only shows up when that program is installed
        let requires = data.get("requires").map(content::scalar).unwrap_or_default();
        if (requires == "lazyvim" && !has_lazyvim()) || (!requires.is_empty() && requires != "lazyvim" && !on_path(&requires)) {
            continue;
        }
        let id = content::scalar(&data["deck"]);
        let mut deck = Deck { id: id.clone(), title: content::scalar(&data["title"]), cards: Vec::new() };
        let text = |c: &Value, key: &str, default: String| c.get(key).map(content::scalar).unwrap_or(default);
        for (i, c) in data["cards"].as_sequence().expect("cards").iter().enumerate() {
            let prompt = content::scalar(&c["prompt"]);
            deck.cards.push(Card {
                deck: id.clone(),
                id: text(c, "id", format!("{id}:{prompt}")),
                answers: c["answer"].as_sequence().expect("answers").iter().map(content::scalar).collect(),
                style: text(&data, "style", "keys".into()),
                case_sensitive: data.get("case_sensitive").and_then(Value::as_bool).unwrap_or(true),
                week: c.get("week").and_then(Value::as_u64).unwrap_or(0) as u32,
                day: c.get("day").and_then(Value::as_u64).unwrap_or(0) as u32,
                note: text(c, "note", text(&data, "note", String::new())),
                order: i,
                prompt,
            });
        }
        decks.insert(id, deck);
    }
    decks
}

/// The decks that need nothing from your machine but files, in teaching order.
pub fn load_static_decks() -> IndexMap<String, Deck> {
    order(static_decks())
}

/// What a command prints, or nothing when it fails or takes more than `seconds`.
pub fn run(program: &str, args: &[&str], seconds: u64) -> String {
    let Ok(mut child) = Command::new(program).args(args).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn() else {
        return String::new();
    };
    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) if started.elapsed() < Duration::from_secs(seconds) => std::thread::sleep(Duration::from_millis(20)),
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return String::new();
            }
        }
    }
    child.wait_with_output().map(|o| String::from_utf8_lossy(&o.stdout).into_owned()).unwrap_or_default()
}

/// Cards from `KEYS → description` lines (the Omarchy keybinding menus).
fn arrow_list(deck: &str, text: &str, case_sensitive: bool) -> Vec<Card> {
    static SKIP: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?i)MOUSE|SCROLL|SWITCH:|XF86").expect("a valid pattern"));
    static NUMBERED: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(.*\D)(\d+)$").expect("a valid pattern"));
    let mut by_desc: IndexMap<String, Vec<String>> = IndexMap::new();
    for line in text.lines() {
        let Some((keys, desc)) = line.split_once('→') else { continue };
        let (keys, desc) = (keys.trim(), desc.trim());
        if keys.is_empty() || desc.is_empty() || SKIP.is_match(keys).unwrap_or(true) {
            continue;
        }
        by_desc.entry(desc.to_string()).or_default().push(keys.to_string());
    }
    let mut cards = Vec::new();
    for (i, (desc, keys)) in by_desc.iter().enumerate() {
        // "Switch to workspace 1..10" is one thing to learn: keep the 1.
        if let Ok(Some(m)) = NUMBERED.captures(desc)
            && &m[2] != "1"
            && by_desc.contains_key(&format!("{}1", &m[1]))
        {
            continue;
        }
        let (prompt, answers) = if keys == &["PREFIX"] {
            // tmux: "PREFIX → CTRL + SPACE / CTRL + B"
            ("The tmux prefix".to_string(), desc.split('/').map(|k| k.trim().to_string()).collect())
        } else {
            (desc.clone(), keys.clone())
        };
        cards.push(Card {
            deck: deck.into(),
            id: format!("{deck}:{prompt}"),
            prompt,
            answers,
            style: "combo".into(),
            case_sensitive,
            order: i,
            ..Card::default()
        });
    }
    cards
}

fn folder(variable: &str, fallback: &str) -> PathBuf {
    std::env::var_os(variable).map(PathBuf::from).unwrap_or_else(|| home().join(fallback))
}

fn newest(path: &std::path::Path, best: &mut f64) {
    let Ok(entries) = std::fs::read_dir(path) else { return };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            newest(&path, best);
        } else if let Ok(modified) = entry.metadata().and_then(|m| m.modified())
            && let Ok(age) = modified.duration_since(std::time::UNIX_EPOCH)
        {
            *best = best.max(age.as_secs_f64());
        }
    }
}

/// Every described keymap in the user's Neovim, cached until the config changes.
fn nvim_keymaps() -> Vec<serde_json::Value> {
    let cache_dir = folder("XDG_CACHE_HOME", ".cache").join("vimniscient");
    if std::fs::create_dir_all(&cache_dir).is_err() {
        return Vec::new();
    }
    let cache = cache_dir.join("nvim-keymaps.json");
    let mut time = 0.0;
    newest(&folder("XDG_CONFIG_HOME", ".config").join("nvim"), &mut time);
    let signature = time.to_string();
    if let Some(data) = std::fs::read_to_string(&cache).ok().and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
        && data["signature"] == signature.as_str()
    {
        return data["maps"].as_array().cloned().unwrap_or_default();
    }
    let out = cache_dir.join("nvim-keymaps.tmp.json");
    let Ok(script) = content::to_temp("nvim/keymaps.lua") else { return Vec::new() };
    let status = Command::new("nvim").args(["--headless", "-i", "NONE", "-n", "-S"]).arg(script)
        .env("VIMNISCIENT_KEYMAPS", &out).current_dir(&cache_dir).stdout(Stdio::null()).stderr(Stdio::null()).status();
    if status.is_err() {
        return Vec::new();
    }
    let Some(maps) = std::fs::read_to_string(&out).ok().and_then(|text| serde_json::from_str::<Vec<serde_json::Value>>(&text).ok()) else {
        return Vec::new();
    };
    let _ = std::fs::remove_file(&out);
    let _ = std::fs::write(cache, serde_json::json!({"signature": signature, "maps": maps}).to_string());
    maps
}

/// The `from_config` keymaps of cards/lazyvim.yaml, as named in the user's config.
fn lazyvim_extra_cards(core: &[Card]) -> Vec<Card> {
    let data: Value = serde_norway::from_str(&content::text("cards/lazyvim.yaml")).expect("lazyvim.yaml");
    let wanted: Vec<String> = data.get("from_config").and_then(Value::as_sequence).map(|k| k.iter().map(|v| pretty_keys(&content::scalar(v))).collect()).unwrap_or_default();
    let known: HashSet<&String> = core.iter().flat_map(|c| &c.answers).collect();
    let by_lhs: IndexMap<String, String> = nvim_keymaps().iter()
        .filter(|m| m["mode"] == "n" && !m["desc"].as_str().unwrap_or("+").starts_with('+'))
        .map(|m| (pretty_keys(m["lhs"].as_str().unwrap_or("")), m["desc"].as_str().unwrap_or("").to_string()))
        .collect();
    wanted.iter().filter(|lhs| by_lhs.contains_key(*lhs) && !known.contains(lhs)).enumerate().map(|(i, lhs)| Card {
        deck: "lazyvim".into(),
        id: format!("lazyvim:{}", by_lhs[lhs]),
        prompt: by_lhs[lhs].clone(),
        answers: vec![lhs.clone()],
        style: "keys".into(),
        case_sensitive: true,
        order: core.len() + i,
        ..Card::default()
    }).collect()
}

/// Every deck, the ones read from this machine included.
pub fn load_decks() -> IndexMap<String, Deck> {
    let mut decks = static_decks();
    for (id, title, cards) in [
        ("omarchy", "Omarchy", arrow_list("omarchy", &run("omarchy", &["menu", "keybindings", "--print"], 20), false)),
        ("tmux", "tmux", arrow_list("tmux", &run("omarchy-menu-tmux-keybindings", &["--print"], 20), true)),
    ] {
        if !cards.is_empty() {
            decks.insert(id.to_string(), Deck { id: id.into(), title: title.into(), cards });
        }
    }
    if let Some(deck) = decks.get_mut("lazyvim") {
        let extra = lazyvim_extra_cards(&deck.cards);
        deck.cards.extend(extra);
    }
    decks.insert("habits".into(), habits::habit_deck());
    order(decks)
}

pub fn order(mut decks: IndexMap<String, Deck>) -> IndexMap<String, Deck> {
    let mut sorted = IndexMap::new();
    for id in DECK_ORDER {
        if let Some(deck) = decks.shift_remove(id) {
            sorted.insert(id.to_string(), deck);
        }
    }
    sorted.extend(decks);
    sorted
}
