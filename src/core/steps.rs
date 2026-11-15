//! A reference solution in steps: `*cgnmatch<Esc>..` is a search, a change, the
//! text you type, and two repeats. Learn shows them as a list ticked off while you
//! type, and `:Hint` gives them out one at a time, so a long answer is a few small
//! moves instead of one string to remember.

use super::mnemonics::{INSERTS, OPERATORS, TABLES};
use regex_lite::Regex;
use std::sync::LazyLock;

#[derive(Clone, Debug, PartialEq)]
pub struct Step {
    pub keys: String,
    pub says: String,
}

/// Keys on their own, where mnemonics.yaml has several on one line ("n N": "next /
/// previous match") or says what a key is called rather than what it does.
const OWN: [(&str, &str); 32] = [
    ("J", "join with the next line"),
    (".", "repeat the last change"),
    ("n", "go to the next match"),
    ("N", "go back to the previous match"),
    ("*", "search for the word under the cursor"),
    ("#", "search back for the word under the cursor"),
    (";", "the same find again"),
    (",", "the same find, backwards"),
    ("u", "undo"),
    ("h", "left"),
    ("j", "down a line"),
    ("k", "up a line"),
    ("l", "right"),
    ("w", "on to the next word"),
    ("o", "open a line below"),
    ("O", "open a line above"),
    ("i", "insert before the cursor"),
    ("a", "append after the cursor"),
    ("p", "put after the cursor"),
    ("P", "put before the cursor"),
    ("D", "delete to the end of the line"),
    ("C", "change to the end of the line"),
    ("cc", "change the whole line"),
    ("S", "change the whole line"),
    ("s", "change one character"),
    ("{", "back to the previous blank line"),
    ("}", "on to the next blank line"),
    ("G", "go to the last line"),
    ("gg", "go to the first line"),
    ("xp", "swap two characters"),
    ("<C-a>", "add 1 to the number"),
    ("<C-x>", "take 1 from the number"),
];
/// What an operator reaches with a motion: "delete" + "to the end of the line".
const REACH: [(&str, &str); 14] = [
    ("w", "to the next word"),
    ("W", "to the next WORD"),
    ("e", "to the end of the word"),
    ("b", "back to the start of the word"),
    ("$", "to the end of the line"),
    ("0", "back to the start of the line"),
    ("^", "back to where the text starts"),
    ("j", "on this line and the next"),
    ("k", "on this line and the one above"),
    ("G", "to the last line"),
    ("gg", "to the first line"),
    ("}", "to the next blank line"),
    ("{", "back to the previous blank line"),
    ("%", "to the matching bracket"),
];
const VERBS: [(&str, &str); 9] = [
    ("c", "change"), ("d", "delete"), ("y", "copy"), ("gU", "uppercase"), ("gu", "lowercase"),
    ("g~", "flip the case of"), (">", "indent"), ("<", "unindent"), ("gc", "comment"),
];
/// In visual mode these act on the selection straight away.
const ON_SELECTION: [(&str, &str); 13] = [
    ("c", "change the selection"), ("d", "delete the selection"), ("x", "delete the selection"),
    ("y", "copy the selection"), ("U", "uppercase the selection"), ("u", "lowercase the selection"),
    ("~", "flip the case of the selection"), (">", "indent the selection"), ("<", "unindent the selection"),
    ("J", "join the selected lines"), ("p", "put over the selection"), ("gc", "comment the selection"),
    ("g<C-a>", "count up through the selection: 1, 2, 3"),
];
/// Ex commands, by what they do.
const EX: [(&str, &str); 10] = [
    (":s", "substitute"), (":g", "on every matching line"), (":v", "on every line that doesn't match"),
    (":m", "move lines"), (":t", "copy lines"), (":d", "delete lines"), (":norm", "type normal-mode keys"),
    (":sort", "sort lines"), (":r", "read in"), (":j", "join lines"),
];
const VISUAL: [(&str, &str); 4] = [("v", "visual: select"), ("V", "visual line: select whole lines"),
    ("<C-v>", "visual block: select a column"), ("gv", "select the last selection again")];

fn lookup(table: &[(&str, &str)], key: &str) -> Option<String> {
    table.iter().find(|(k, _)| *k == key).map(|(_, v)| (*v).to_string())
}

fn tokens(s: &str) -> Vec<String> {
    let chars: Vec<char> = s.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let close = (chars[i] == '<').then(|| chars[i + 1..].iter().position(|&c| c == '>' || c == '<' || c == ' ')).flatten();
        if let Some(len) = close.filter(|&n| n > 0 && chars[i + 1 + n] == '>') {
            out.push(chars[i..i + len + 2].iter().collect());
            i += len + 2;
        } else {
            out.push(chars[i].to_string());
            i += 1;
        }
    }
    out
}

/// What Vim calls `key`, without the asides ("go to last line (or line N)").
fn means(key: &str) -> String {
    lookup(&OWN, key).unwrap_or_else(|| {
        let full = TABLES.means.get(key).cloned().unwrap_or_default();
        full.split(" (").next().unwrap_or_default().to_string()
    })
}

/// The longest key from `candidates` that the tokens spell from `at`: (key, tokens).
fn longest<'a>(toks: &[String], at: usize, candidates: impl Iterator<Item = &'a str>) -> Option<(String, usize)> {
    let mut best: Option<(String, usize)> = None;
    for key in candidates {
        let parts = tokens(key);
        if !parts.is_empty() && toks.len() >= at + parts.len() && toks[at..at + parts.len()] == parts[..] && best.as_ref().is_none_or(|b| parts.len() > b.1) {
            best = Some((key.to_string(), parts.len()));
        }
    }
    best
}

fn until(toks: &[String], from: usize, end: &str) -> usize {
    toks[from.min(toks.len())..].iter().position(|t| t == end).map_or(toks.len(), |p| from + p)
}

fn quoted(toks: &[String]) -> String {
    format!("“{}”", toks.concat())
}

fn article(noun: &str) -> &'static str {
    if noun.starts_with(['a', 'e', 'i', 'o', 'u']) { "an" } else { "a" }
}

/// A key that takes one character after it: f{char}, ma, @a, r{char} ...
fn with_char(key: &str, c: &str) -> Option<String> {
    let q = format!("“{c}”");
    Some(match key {
        "f" => format!("find {q}"),
        "t" => format!("go till {q}"),
        "F" => format!("find {q} backwards"),
        "T" => format!("go back till {q}"),
        "r" => format!("replace the character with {q}"),
        "m" => format!("set mark {c} here"),
        "`" | "'" if c == key => "jump back to where you were".into(),
        "'" => format!("jump to mark {c}'s line"),
        "`" => format!("jump to mark {c}"),
        "@" if c == "@" => "play the last macro again".into(),
        "@" => format!("play the macro in register {c}"),
        _ => return None,
    })
}

/// An Ex command up to its Enter: what it is, from its name and range.
fn ex(command: &str) -> String {
    static NAME: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^:([%.$,\d'<>+-]*)\s*([a-zA-Z]+|!)").expect("a valid pattern"));
    let Some(caps) = NAME.captures(command) else { return "run the command".into() };
    let name = &caps[2];
    let names = EX.iter().map(|(k, _)| *k).chain(TABLES.means.keys().map(String::as_str));
    let found = names.filter(|k| k.starts_with(':') && (&k[1..] == name || (k[1..].starts_with(name) && name.len() > 1)))
        .min_by_key(|k| k.len()).map(|k| lookup(&EX, k).unwrap_or_else(|| means(k)));
    let what = found.or_else(|| (name == "!").then(|| "filter through a shell command".to_string())).unwrap_or_else(|| format!("run :{name}"));
    let range = &caps[1];
    if range.contains('%') { format!("{what}, on every line") } else if range.is_empty() { what } else { format!("{what} ({range})") }
}

/// What you type after a change or insert, up to and including <Esc>.
fn typing(toks: &[String], from: usize, out: &mut Vec<Step>) -> usize {
    let end = until(toks, from, "<Esc>");
    let text = &toks[from.min(end)..end];
    let says = match (text.is_empty(), end < toks.len()) {
        (true, true) => "Esc, back to normal mode".to_string(),
        (true, false) => return from,
        (false, true) => format!("type {}, then Esc", quoted(text)),
        (false, false) => format!("type {}", quoted(text)),
    };
    let stop = (end + 1).min(toks.len());
    out.push(Step { keys: toks[from..stop].concat(), says });
    stop
}

/// What an operator acts on, from `at`: (how many tokens, a phrase).
fn target(toks: &[String], at: usize, op: &str) -> (usize, String) {
    let Some(first) = toks.get(at) else { return (0, String::new()) };
    let op_parts = tokens(op);
    if !op_parts.is_empty() && (toks[at..].starts_with(&op_parts) || (op_parts.len() > 1 && op_parts.last() == Some(first))) {
        let n = if toks[at..].starts_with(&op_parts) { op_parts.len() } else { 1 }; // dd, gUU
        return (n, "the whole line".into());
    }
    if first.len() == 1 && first.chars().all(|c| c.is_ascii_digit()) && first != "0" {
        let (used, what) = target(toks, at + 1, op);
        return (used + 1, format!("{what}, {first} times"));
    }
    if (first == "i" || first == "a") && at + 1 < toks.len() {
        let object = TABLES.object_means.get(&toks[at + 1]).cloned().unwrap_or_else(|| toks[at + 1].clone());
        let object = object.split(" (").next().unwrap_or_default().to_string();
        let which = if first == "i" { "inner" } else { article(&object) };
        return (2, format!("{which} {object}"));
    }
    if first == "/" || first == "?" {
        let end = until(toks, at + 1, "<CR>");
        let back = if first == "?" { "back " } else { "" };
        return ((end + 1).min(toks.len()) - at, format!("{back}up to {}", quoted(&toks[at + 1..end])));
    }
    if let Some(c) = toks.get(at + 1) {
        let phrase = match first.as_str() {
            "f" => Some(format!("up to and including “{c}”")),
            "t" => Some(format!("up to “{c}”")),
            "F" => Some(format!("back to and including “{c}”")),
            "T" => Some(format!("back to just after “{c}”")),
            "'" => Some(format!("to mark {c}'s line")),
            "`" => Some(format!("to mark {c}")),
            "g" if c == "n" => Some("the next match".into()),
            "g" if c == "N" => Some("the previous match".into()),
            _ => None,
        };
        if let Some(phrase) = phrase {
            return (2, phrase);
        }
    }
    if op == "c" && first == "w" {
        return (1, "to the end of the word".into()); // cw works like ce
    }
    let keys = TABLES.means.keys().map(String::as_str).chain(REACH.iter().map(|(k, _)| *k)).filter(|k| !k.starts_with(':'));
    match longest(toks, at, keys) {
        Some((key, n)) => (n, lookup(&REACH, &key).unwrap_or_else(|| format!("to {}", means(&key)))),
        None => (1, String::new()),
    }
}

/// The steps of `solution`, in order: together their keys are the solution.
pub fn steps(solution: &str) -> Vec<Step> {
    if solution == "—" {
        return Vec::new();
    }
    let toks = tokens(solution);
    let mut out: Vec<Step> = Vec::new();
    let (mut visual, mut recording) = (false, false);
    let mut i = 0;
    let mut prefix = String::new(); // a count or a register, said with what follows
    let mut lead = String::new();
    while i < toks.len() {
        let t = toks[i].as_str();
        let digit = t.len() == 1 && t.chars().all(|c| c.is_ascii_digit());
        if digit && (t != "0" || !prefix.is_empty()) {
            prefix.push_str(t);
            lead = format!("{prefix}× ");
            i += 1;
            continue;
        }
        if t == "\"" && i + 1 < toks.len() {
            prefix.push_str(&toks[i..i + 2].concat());
            lead = format!("register {}: ", toks[i + 1]);
            i += 2;
            continue;
        }
        let start = i;
        let says;
        let mut then_type = false;
        let one = |i: usize| toks.get(i + 1).cloned().unwrap_or_default();
        if t == "/" || t == "?" || t == ":" {
            let end = until(&toks, i + 1, "<CR>");
            let body = &toks[i + 1..end];
            says = match t {
                ":" => ex(&toks[i..end].concat()),
                _ if body.is_empty() => "search again for the last pattern".into(),
                "/" => format!("search for {}", quoted(body)),
                _ => format!("search back for {}", quoted(body)),
            };
            i = (end + 1).min(toks.len());
            visual = false;
        } else if t == "q" && recording {
            says = "stop recording".into();
            recording = false;
            i += 1;
        } else if t == "q" && i + 1 < toks.len() {
            says = format!("record what follows into register {}", one(i));
            recording = true;
            i += 2;
        } else if let Some((key, n)) = longest(&toks, i, VISUAL.iter().map(|(k, _)| *k)).filter(|_| !visual) {
            says = lookup(&VISUAL, &key).unwrap_or_default();
            visual = true;
            i += n;
        } else if visual && (t == "i" || t == "a") && i + 1 < toks.len() {
            let (n, what) = target(&toks, i, "");
            says = format!("select {what}");
            i += n;
        } else if let Some((key, n)) = longest(&toks, i, ON_SELECTION.iter().map(|(k, _)| *k)).filter(|_| visual) {
            says = lookup(&ON_SELECTION, &key).unwrap_or_default();
            then_type = key == "c";
            visual = false;
            i += n;
        } else if let Some((op, n)) = longest(&toks, i, OPERATORS.iter().copied())
            .filter(|(op, n)| !(op == "c" && toks.get(i + n).is_some_and(|t| t == "c"))) // cc types a line
        {
            let (used, what) = target(&toks, i + n, &op);
            let verb = lookup(&VERBS, &op).unwrap_or_else(|| op.clone());
            says = format!("{verb} {what}").trim_end().to_string();
            i += n + used;
            then_type = op == "c";
        } else if let Some((key, n)) = longest(&toks, i, INSERTS.iter().copied()) {
            says = means(&key);
            i += n;
            then_type = true;
            visual = false;
        } else if let Some(text) = with_char(t, &one(i)).filter(|_| i + 1 < toks.len()) {
            says = text;
            i += 2;
        } else if let Some((key, n)) = longest(&toks, i, TABLES.means.keys().map(String::as_str).chain(OWN.iter().map(|(k, _)| *k)).filter(|k| !k.starts_with(':'))) {
            i += n;
            // the same key again: n n, . . .
            let mut times = 1;
            while toks.get(i).is_some_and(|t| *t == key) {
                times += 1;
                i += 1;
            }
            let base = means(&key);
            says = if times > 1 { format!("{base}, {times} times") } else { base };
        } else {
            says = String::new();
            i += 1;
        }
        out.push(Step { keys: format!("{prefix}{}", toks[start..i].concat()), says: format!("{lead}{says}") });
        prefix.clear();
        lead.clear();
        if then_type {
            i = typing(&toks, i, &mut out);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn said(solution: &str) -> Vec<(String, String)> {
        steps(solution).into_iter().map(|s| (s.keys, s.says)).collect()
    }

    fn pairs(list: &[(&str, &str)]) -> Vec<(String, String)> {
        list.iter().map(|(k, s)| (k.to_string(), s.to_string())).collect()
    }

    #[test]
    fn cgn_in_steps() {
        assert_eq!(said("*cgnmatch<Esc>.."), pairs(&[
            ("*", "search for the word under the cursor"),
            ("cgn", "change the next match"),
            ("match<Esc>", "type “match”, then Esc"),
            ("..", "repeat the last change, 2 times"),
        ]));
        assert_eq!(said("*Ncgna<Esc>nn."), pairs(&[
            ("*", "search for the word under the cursor"),
            ("N", "go back to the previous match"),
            ("cgn", "change the next match"),
            ("a<Esc>", "type “a”, then Esc"),
            ("nn", "go to the next match, 2 times"),
            (".", "repeat the last change"),
        ]));
        assert_eq!(said("/the last<CR>cgnthe next<Esc>."), pairs(&[
            ("/the last<CR>", "search for “the last”"),
            ("cgn", "change the next match"),
            ("the next<Esc>", "type “the next”, then Esc"),
            (".", "repeat the last change"),
        ]));
        assert_eq!(said("/um, <CR>dgn..")[1], ("dgn".into(), "delete the next match".into()));
    }

    #[test]
    fn other_shapes() {
        assert_eq!(said("ciwquick<Esc>"), pairs(&[("ciw", "change inner word"), ("quick<Esc>", "type “quick”, then Esc")]));
        assert_eq!(said("d/S<CR>"), pairs(&[("d/S<CR>", "delete up to “S”")]));
        assert_eq!(said("2dd"), pairs(&[("2dd", "2× delete the whole line")]));
        assert_eq!(said("dt,")[0].1, "delete up to “,”");
        assert_eq!(said("dG")[0].1, "delete to the last line");
        assert_eq!(said("A;<Esc>")[1].0, ";<Esc>");
        assert_eq!(said("viwp"), pairs(&[("v", "visual: select"), ("iw", "select inner word"), ("p", "put over the selection")]));
        assert_eq!(said("Vu")[1].1, "lowercase the selection");
        assert_eq!(said("qaA;<Esc>jq3@a"), pairs(&[
            ("qa", "record what follows into register a"), ("A", "append at line end"), (";<Esc>", "type “;”, then Esc"),
            ("j", "down a line"), ("q", "stop recording"), ("3@a", "3× play the macro in register a"),
        ]));
        assert_eq!(said(":%s/u//g<CR>"), pairs(&[(":%s/u//g<CR>", "substitute, on every line")]));
        assert_eq!(said(":g/DEBUG/d<CR>:%s/^\\S\\+ //<CR>").len(), 2);
        assert_eq!(said("\"ayy")[0].1, "register a: copy the whole line");
    }

    #[test]
    fn steps_spell_the_solution() {
        for lesson in crate::core::lessons::LESSONS.iter() {
            for task in lesson.tasks.iter().flat_map(|t| t.siblings.iter()) {
                let found = steps(&task.solution);
                let joined: String = found.iter().map(|s| s.keys.as_str()).collect();
                assert_eq!(joined, task.solution, "{}", lesson.id);
                assert!(found.iter().all(|s| !s.says.is_empty()), "{}: {found:?}", lesson.id);
            }
        }
    }

    #[test]
    #[ignore]
    fn print_all() {
        for lesson in crate::core::lessons::LESSONS.iter() {
            for task in &lesson.tasks {
                let s: Vec<String> = steps(&task.solution).iter().map(|s| format!("{} = {}", s.keys, s.says)).collect();
                println!("{}#{} {}  |  {}", lesson.id, task.index, task.solution, s.join("  ·  "));
            }
        }
    }
}
