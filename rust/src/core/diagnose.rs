//! What your own keys say about your strategy, on the results screen. A few
//! rules, each one certain from the keys alone, so a task with nothing clear to
//! say says nothing. They only speak when you went over the reference, and never
//! about text you typed in insert mode.

use super::keys::split_keys;
use fancy_regex::Regex;
use std::sync::LazyLock;

const MOTION_RUN: usize = 4; // jjjj; Vjj in a reference is fine, and three presses aren't a habit
const X_RUN: usize = 3;
const MOTIONS: [&str; 7] = ["h", "j", "k", "l", "w", "b", "e"];
const OPERATORS: [&str; 6] = ["c", "d", "y", ">", "<", "="];
const TAKES_CHAR: [&str; 10] = ["f", "t", "F", "T", "r", "m", "'", "`", "@", "\""];
const INSERTS: [&str; 10] = ["i", "a", "A", "I", "o", "O", "s", "S", "C", "R"];

fn skip_until(tokens: &[String], mut i: usize, stop: &str) -> usize {
    while i < tokens.len() && tokens[i] != stop {
        i += 1;
    }
    i + 1
}

/// Past what follows an operator: a count, then a motion or a text object.
fn skip_motion(tokens: &[String], mut i: usize) -> usize {
    while i < tokens.len() && tokens[i].chars().all(char::is_numeric) {
        i += 1;
    }
    if i >= tokens.len() {
        return i;
    }
    let key = tokens[i].as_str();
    if matches!(key, "/" | "?") {
        return skip_until(tokens, i + 1, "<CR>");
    }
    i + if matches!(key, "i" | "a" | "g" | "f" | "t" | "F" | "T" | "'" | "`") { 2 } else { 1 }
}

/// The runs of keys pressed as commands: not typed text, search or `:` lines.
pub fn normal_keys(keys: &str) -> Vec<Vec<String>> {
    let tokens = split_keys(keys);
    let (mut runs, mut run): (Vec<Vec<String>>, Vec<String>) = (Vec::new(), Vec::new());
    let (mut i, mut visual, mut recording) = (0, false, false);
    while i < tokens.len() {
        let key = tokens[i].as_str();
        i += 1;
        if matches!(key, ":" | "/" | "?") {
            i = skip_until(&tokens, i, "<CR>");
            visual = false;
        } else if visual && matches!(key, "c" | "s" | "I" | "A") {
            i = skip_until(&tokens, i, "<Esc>");
            visual = false;
        } else if visual && (OPERATORS.contains(&key) || matches!(key, "x" | "J" | "U" | "u" | "<Esc>")) {
            visual = false;
        } else if OPERATORS.contains(&key) {
            if tokens.get(i).is_some_and(|next| next == key) {
                i += 1; // dd, cc, yy
            } else {
                i = skip_motion(&tokens, i);
            }
            if key == "c" {
                i = skip_until(&tokens, i, "<Esc>");
            }
        } else if key == "g" && tokens.get(i).is_some_and(|next| matches!(next.as_str(), "U" | "u" | "~")) {
            i = skip_motion(&tokens, i + 1);
        } else if key == "g" || TAKES_CHAR.contains(&key) {
            i += 1;
        } else if key == "q" {
            i += usize::from(!recording);
            recording = !recording;
        } else if INSERTS.contains(&key) {
            i = skip_until(&tokens, i, "<Esc>");
        } else {
            visual = visual || matches!(key, "v" | "V" | "<C-v>");
            run.push(key.to_string());
            continue;
        }
        if !run.is_empty() {
            runs.push(std::mem::take(&mut run));
        }
    }
    if !run.is_empty() {
        runs.push(run);
    }
    runs
}

fn longest_run(runs: &[Vec<String>], wanted: &[&str]) -> (String, usize) {
    let (mut best, mut length) = (String::new(), 0);
    for tokens in runs {
        let (mut last, mut n) = ("", 0);
        for key in tokens {
            n = if key == last { n + 1 } else { 1 };
            last = key;
            if wanted.contains(&key.as_str()) && n > length {
                (best, length) = (key.clone(), n);
            }
        }
    }
    (best, length)
}

/// One thing worth saying about how `keys` went about it, or nothing.
pub fn diagnose(keys: &str, count: usize, reference: usize) -> String {
    static REPEAT: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?s)((?:<[^<>\s]+>|.){3,}?)\1\1").expect("a valid pattern"));
    if count <= reference {
        return String::new();
    }
    let runs = normal_keys(keys);
    let (motion, length) = longest_run(&runs, &MOTIONS);
    if length >= MOTION_RUN {
        let better = if matches!(motion.as_str(), "h" | "l") { "f, t, / or a count" } else { "a count" };
        return format!("{motion} {length} times in a row: {better} gets there in one go.");
    }
    if longest_run(&runs, &["x"]).1 >= X_RUN {
        return "x over and over: a count, dw or diw takes it all at once.".into();
    }
    if let Ok(Some(caps)) = REPEAT.captures(keys) {
        let part = &caps[1];
        if !runs.iter().any(|run| run.iter().any(|key| key == ".")) && part.contains("<Esc>") {
            return format!("You typed {part} three times: . repeats the last change.");
        }
    }
    String::new()
}
