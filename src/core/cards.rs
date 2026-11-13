//! Flashcard decks. The static ones come from `cards/*.yaml`; a deck about a
//! program only shows up when that program is installed.

use super::{answer::display_keys, content, habits};
use fancy_regex::Regex;
use indexmap::IndexMap;
use serde_norway::Value;
use std::path::PathBuf;
use std::io::Read;
use std::process::{Command, Output, Stdio};
use std::sync::LazyLock;
use std::time::{Duration, Instant};

// New cards are introduced round-robin in this order.
pub const DECK_ORDER: [&str; 6] = ["habits", "vim", "omarchy", "shell", "foot", "zathura"];

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
        display_keys(&self.answers[0])
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
        let id = content::scalar(&data["deck"]);
        // Keep the optional lesson material, but do not introduce LazyVim cards.
        if id == "lazyvim" {
            continue;
        }
        let requires = data.get("requires").map(content::scalar).unwrap_or_default();
        if !requires.is_empty() && !on_path(&requires) {
            continue;
        }
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

/// Run `command` to the end, at most `seconds`; None when it won't start or is too slow.
/// Its output is read while it runs, so a long one can't fill the pipe and stall.
pub fn output_within(command: &mut Command, seconds: u64) -> Option<Output> {
    fn drain(pipe: Option<impl Read + Send + 'static>) -> std::thread::JoinHandle<Vec<u8>> {
        std::thread::spawn(move || {
            let mut bytes = Vec::new();
            if let Some(mut pipe) = pipe {
                let _ = pipe.read_to_end(&mut bytes);
            }
            bytes
        })
    }
    let mut child = command.stdin(Stdio::null()).spawn().ok()?;
    let (stdout, stderr) = (drain(child.stdout.take()), drain(child.stderr.take()));
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if started.elapsed() < Duration::from_secs(seconds) => std::thread::sleep(Duration::from_millis(20)),
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
        }
    };
    let (stdout, stderr) = (stdout.join().unwrap_or_default(), stderr.join().unwrap_or_default());
    status.map(|status| Output { status, stdout, stderr })
}

/// What a command prints, or nothing when it fails or takes more than `seconds`.
pub fn run(program: &str, args: &[&str], seconds: u64) -> String {
    output_within(Command::new(program).args(args).stdout(Stdio::piped()).stderr(Stdio::null()), seconds)
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default()
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
        cards.push(Card {
            deck: deck.into(),
            id: format!("{deck}:{desc}"),
            prompt: desc.clone(),
            answers: keys.clone(),
            style: "combo".into(),
            case_sensitive,
            order: i,
            ..Card::default()
        });
    }
    cards
}

/// Active review decks, including this machine's desktop bindings.
pub fn load_decks() -> IndexMap<String, Deck> {
    let mut decks = static_decks();
    for (id, title, cards) in [
        ("omarchy", "Omarchy", arrow_list("omarchy", &run("omarchy", &["menu", "keybindings", "--print"], 20), false)),
    ] {
        if !cards.is_empty() {
            decks.insert(id.to_string(), Deck { id: id.into(), title: title.into(), cards });
        }
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
