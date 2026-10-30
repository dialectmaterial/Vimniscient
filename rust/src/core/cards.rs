//! Flashcard decks. The static ones come from `cards/*.yaml`; a deck about a
//! program only shows up when that program is installed.

use super::{answer::pretty_keys, content};
use indexmap::IndexMap;
use serde_norway::Value;
use std::path::PathBuf;

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
