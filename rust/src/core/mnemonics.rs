//! What keys stand for: `mnemonics.yaml` read as tables, and `hooks`, which splits
//! a key sequence like `ciw` or `:%s//x/g` into its parts and returns the hook for
//! each one. Shown after an answer, never before (it names the keys).

use super::content;
use fancy_regex::Regex;
use indexmap::IndexMap;
use std::sync::LazyLock;

pub const OPERATORS: [&str; 9] = ["c", "d", "y", "gU", "gu", "g~", ">", "<", "gc"];
// keys that take one character after them: f{char}, ma, "a, @a, r{char} ...
const TAKES_CHAR: [&str; 11] = ["f", "t", "F", "T", "m", "'", "`", "q", "@", "r", "<C-r>"];
// keys that leave you typing text until <Esc>
const INSERTS: [&str; 11] = ["i", "a", "A", "I", "o", "O", "R", "C", "s", "S", "cc"];
const PAIRS: &str = "()[]{}<>\"'`";
const MAX_HOOKS: usize = 4;

pub struct Tables {
    pub normal: IndexMap<String, String>,
    pub objects: IndexMap<String, String>,
    pub ex: IndexMap<String, String>,
    pub means: Vec<(String, String, String)>, // key as written, means, hook
}

pub static TABLES: LazyLock<Tables> = LazyLock::new(|| {
    let data: serde_norway::Mapping = serde_norway::from_str(&content::text("mnemonics.yaml")).expect("mnemonics.yaml");
    let (mut normal, mut objects, mut ex, mut means) = (IndexMap::new(), IndexMap::new(), IndexMap::new(), Vec::new());
    for (key, entry) in &data {
        let key = content::scalar(key);
        let hook = entry.get("hook").map(content::scalar).unwrap_or_default();
        means.push((key.clone(), entry.get("means").map(content::scalar).unwrap_or_default(), hook.clone()));
        let (name, kind) = key.split_once(" (").unwrap_or((&key, ""));
        let kind = kind.trim_end_matches(')');
        match kind {
            "object" => {
                objects.insert(name.to_string(), hook);
            }
            "range" => {
                ex.insert("%".to_string(), hook);
            }
            "insert" => {
                normal.insert("a (insert)".to_string(), hook);
            }
            "motion" | "" => {
                if kind.is_empty() && matches!(name, "w" | "W" | "s") {
                    objects.insert(name.to_string(), hook.clone());
                }
                // "h j k l", "n N", "( b": several keys sharing one hook
                let parts: Vec<&str> = if name.contains(' ') && !name.starts_with(':') { name.split(' ').collect() } else { vec![name] };
                for part in parts {
                    let table = if part.starts_with(':') { &mut ex } else { &mut normal };
                    table.insert(part.to_string(), hook.clone());
                }
            }
            _ => {}
        }
    }
    let round = objects.get("(").cloned().unwrap_or_default();
    for c in PAIRS.chars() {
        objects.entry(c.to_string()).or_insert_with(|| round.clone());
    }
    Tables { normal, objects, ex, means }
});

/// The hooks for the parts of `keys`, in order, without repeats.
pub fn hooks(keys: &str) -> Vec<String> {
    let found = if keys.starts_with(':') { ex_hooks(keys) } else { normal_hooks(keys) };
    let mut seen: Vec<String> = Vec::new();
    for hook in found {
        if !hook.is_empty() && !seen.contains(&hook) {
            seen.push(hook);
        }
    }
    seen.truncate(MAX_HOOKS);
    seen
}

fn find_from(keys: &[char], needle: &str, from: usize) -> Option<usize> {
    let needle: Vec<char> = needle.chars().collect();
    (from..keys.len().saturating_sub(needle.len() - 1)).find(|&i| keys[i..].starts_with(&needle))
}

fn starts(keys: &[char], at: usize, token: &str) -> bool {
    let token: Vec<char> = token.chars().collect();
    at <= keys.len() && keys[at..].starts_with(&token)
}

fn skip_insert(keys: &[char], i: usize) -> usize {
    find_from(keys, "<Esc>", i).map_or(keys.len(), |end| end + 5)
}

fn normal_hooks(text: &str) -> Vec<String> {
    let t = &*TABLES;
    let keys: Vec<char> = text.chars().collect();
    let hook = |name: &str| t.normal.get(name).cloned().unwrap_or_default();
    let mut by_length: Vec<&String> = t.normal.keys().collect();
    by_length.sort_by_key(|k| std::cmp::Reverse(k.chars().count()));
    let mut out = Vec::new();
    let mut i = 0;
    let mut operator = String::new();
    while i < keys.len() {
        let first = keys[i];
        if first == ':' {
            // a command inside a sequence, like *:%s//x/g
            let end = find_from(&keys, "<CR>", i);
            let command: String = keys[i..end.unwrap_or(keys.len())].iter().collect();
            out.extend(ex_hooks(&command));
            i = end.map_or(keys.len(), |e| e + 4);
            continue;
        }
        if first.is_ascii_digit() && !(first == '0' && !(i > 0 && keys[i - 1].is_ascii_digit())) {
            i += 1; // a count
            continue;
        }
        if first == '"' && i + 1 < keys.len() {
            // a register
            let name: String = keys[i..i + 2].iter().collect();
            let found = [hook(&name), hook(&name.to_lowercase()), hook("\"")];
            out.push(found.into_iter().find(|h| !h.is_empty()).unwrap_or_default());
            i += 2;
            continue;
        }
        if !operator.is_empty() && matches!(first, 'i' | 'a') && i + 1 < keys.len() {
            // a text object
            out.push(hook(&first.to_string()));
            out.push(t.objects.get(&keys[i + 1].to_string()).cloned().unwrap_or_default());
            i += 2;
            if operator == "c" {
                i = skip_insert(&keys, i);
            }
            operator.clear();
            continue;
        }
        let Some(token) = by_length.iter().find(|k| !k.contains(' ') && starts(&keys, i, k)) else {
            i += 1;
            continue;
        };
        let token = token.as_str();
        if token == "a" && operator.is_empty() {
            out.push(hook("a (insert)"));
        } else if token != "i" || !operator.is_empty() {
            out.push(hook(token));
        }
        i += token.chars().count();
        if TAKES_CHAR.contains(&token) && i < keys.len() {
            i += if starts(&keys, i, "<CR>") { 4 } else { 1 };
        }
        if matches!(token, "/" | "?") {
            i = find_from(&keys, "<CR>", i).map_or(keys.len(), |e| e + 4);
        }
        if operator == "c" || INSERTS.contains(&token) {
            i = skip_insert(&keys, i);
            operator.clear();
        } else if OPERATORS.contains(&token) && operator.is_empty() {
            operator = token.to_string();
            let double = if starts(&keys, i, token) { token.to_string() } else { token.chars().last().unwrap_or(' ').to_string() };
            if starts(&keys, i, &double) {
                // dd, >>, guu, gcc: the whole line
                out.push(hook("dd"));
                i += double.chars().count();
                operator.clear();
            }
        } else {
            operator.clear();
        }
    }
    out
}

fn ex_hooks(command: &str) -> Vec<String> {
    static SPAN: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^([%.$,\d'<>+-]*)\s*([a-zA-Z]+|!)").expect("a valid pattern"));
    let ex = &TABLES.ex;
    let hook = |name: &str| ex.get(name).cloned().unwrap_or_default();
    let mut out = Vec::new();
    let body = command.trim_start_matches(':');
    let Ok(Some(caps)) = SPAN.captures(body) else {
        return out;
    };
    let (span, name) = (&caps[1], &caps[2]);
    if span.contains('%') {
        out.push(hook("%"));
    }
    // the longest command name that this abbreviation starts (:s, :sort, :norm, :g)
    let candidates = ex.keys().filter(|n| n.starts_with(':')).filter(|n| &n[1..] == name || (n[1..].starts_with(name) && name.chars().count() > 1));
    let best = candidates.min_by_key(|n| n.chars().count());
    if let Some(best) = best {
        out.push(hook(best));
    } else if name == "!" || body.trim_start_matches('%').starts_with('!') {
        out.push(hook(":!"));
    }
    if body[caps.get(0).map_or(0, |m| m.end())..].contains("norm") {
        out.push(hook(":norm"));
    }
    for token in ["\\v", "&", "\\1"] {
        if body.contains(token) {
            out.push(hook(token));
        }
    }
    out
}
