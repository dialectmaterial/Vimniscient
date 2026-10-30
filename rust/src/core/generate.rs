//! Practice texts made from a seed, for skills where any sentence will do.
//!
//! A lesson task can name a `generate` kind. Its Learn round keeps the written text;
//! Recall and reviews can get a generated one, so a skill gets practised on sentences
//! you haven't seen. The same seed always gives the same task. The sentences are the
//! hooks of the keys week 1 teaches: nothing about keys you haven't met yet.

use super::lessons::{LESSONS, Task};
use super::mnemonics::{TABLES, hooks};
use fancy_regex::Regex;
use std::collections::HashSet;
use std::sync::LazyLock;

/// A small random generator of our own (FNV-1a into SplitMix64), so a seed gives the
/// same text whatever a library does next year.
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: &str) -> Rng {
        Rng(seed.bytes().fold(0xcbf2_9ce4_8422_2325, |hash, byte| (hash ^ u64::from(byte)).wrapping_mul(0x0100_0000_01b3)))
    }

    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        z ^ (z >> 31)
    }

    pub fn below(&mut self, n: usize) -> usize {
        (self.next() % n.max(1) as u64) as usize
    }

    pub fn between(&mut self, low: usize, high: usize) -> usize {
        low + self.below(high - low + 1)
    }

    pub fn coin(&mut self) -> bool {
        self.next() & 1 == 0
    }

    pub fn choice<'a, T>(&mut self, items: &'a [T]) -> &'a T {
        &items[self.below(items.len())]
    }

    pub fn shuffle<T>(&mut self, items: &mut [T]) {
        for i in (1..items.len()).rev() {
            items.swap(i, self.below(i + 1));
        }
    }

    pub fn sample<T: Clone>(&mut self, items: &[T], n: usize) -> Vec<T> {
        let mut pool = items.to_vec();
        self.shuffle(&mut pool);
        pool.truncate(n);
        pool
    }
}

const FILLER: [&str; 4] = ["um", "well", "like", "so"];

struct Made {
    goal: String,
    start: Vec<String>,
    cursor: (usize, usize),
    target: Vec<String>,
    solution: String,
    hint: String,
}

static SENTENCES: LazyLock<Vec<String>> = LazyLock::new(|| {
    let known: HashSet<String> = LESSONS.iter().filter(|l| l.week == 1).flat_map(|l| l.keys.iter()).flat_map(|key| hooks(key)).collect();
    let mut seen = HashSet::new();
    TABLES.normal.values().chain(TABLES.objects.values())
        .filter(|hook| known.contains(*hook) && seen.insert(hook.to_string()))
        // as written: a capital would change the key ("u is down" is not "U is down")
        .map(|hook| if hook.ends_with('.') { hook.clone() } else { format!("{hook}.") })
        .collect()
});

/// Single-letter keys with a one-word meaning: (c, change), (d, delete) ...
static MEANINGS: LazyLock<Vec<(String, String)>> = LazyLock::new(|| {
    let known: HashSet<&str> = SENTENCES.iter().map(|s| s.trim_end_matches('.')).collect();
    TABLES.means.iter()
        .filter(|(key, means, hook)| {
            known.contains(hook.trim_end_matches('.')) && key.len() == 1 && key.chars().all(|c| c.is_ascii_alphabetic())
                && !means.is_empty() && means.chars().all(|c| c.is_ascii_lowercase())
        })
        .map(|(key, means, _)| (key.clone(), means.clone()))
        .collect()
});

fn with_gaps() -> Vec<&'static String> {
    SENTENCES.iter().filter(|s| !gaps(s).is_empty()).collect()
}

/// Where a new word can go: the start of every word but the first.
fn gaps(sentence: &str) -> Vec<usize> {
    let bytes = sentence.as_bytes();
    (1..bytes.len()).filter(|&i| bytes[i - 1] == b' ' && bytes[i].is_ascii_alphabetic()).collect()
}

fn words(sentence: &str, spaced: bool) -> Vec<(usize, usize)> {
    static WORD: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?<![\w'.-])[A-Za-z]{4,}(?![\w'-])").expect("a valid pattern"));
    let bytes = sentence.as_bytes();
    WORD.find_iter(sentence).flatten().map(|m| (m.start(), m.end()))
        .filter(|&(start, end)| {
            if spaced { start > 0 && bytes[start - 1] == b' ' && end < bytes.len() && bytes[end] == b' ' } else { end < bytes.len() }
        })
        .collect()
}

fn lines(rng: &mut Rng, n: usize) -> Vec<String> {
    rng.sample(&SENTENCES, n)
}

fn made(goal: impl Into<String>, start: Vec<String>, cursor: (usize, usize), target: Vec<String>, solution: impl Into<String>, hint: impl Into<String>) -> Made {
    Made { goal: goal.into(), start, cursor, target, solution: solution.into(), hint: hint.into() }
}

fn each(rng: &mut Rng, change: impl Fn(&str) -> String, keys: &str, goal: &str, hint: &str) -> Made {
    let start = lines(rng, 3);
    let target = start.iter().map(|line| change(line)).collect();
    made(goal, start, (1, 0), target, keys, hint)
}

fn some(rng: &mut Rng, n: usize, cursor: (usize, usize), keys: &str, goal: &str, hint: &str, target: impl Fn(&[String]) -> Vec<String>) -> Made {
    let start = lines(rng, n);
    let target = target(&start);
    made(goal, start, cursor, target, keys, hint)
}

fn marked(rng: &mut Rng, sentence: &str) -> String {
    let gap = *rng.choice(&gaps(sentence));
    format!("{}#{}", &sentence[..gap], &sentence[gap..])
}

fn nav(rng: &mut Rng, up: bool) -> Made {
    let n = rng.between(4, 11);
    let pool = with_gaps();
    let target: Vec<String> = (0..=n).map(|_| rng.choice(&pool).to_string()).collect();
    let (far, near) = if up { (0, n) } else { (n, 0) };
    let mut start = target.clone();
    start[far] = marked(rng, &target[far]);
    let key = if up { 'k' } else { 'j' };
    made("Delete the #.", start, (near + 1, 0), target, format!("{n}{key}f#x"), format!("The line numbers say how far: {n}{key}, then f# and x."))
}

fn paren(rng: &mut Rng, around: bool) -> Made {
    let name = *rng.choice(if around { &["around", "parens"] } else { &["inner", "inside"] });
    let args: Vec<String> = rng.sample(&MEANINGS, 3).into_iter().map(|(_, means)| means).collect();
    let args = args.join(", ");
    let (target, keys, what) = if around {
        (format!("{name} + 1"), "da(", "the call's parentheses and arguments")
    } else {
        (format!("{name}() + 1"), "di(", "the arguments, keeping the parentheses")
    };
    made(format!("Delete {what}."), vec![format!("{name}({args}) + 1")], (1, name.len() + 1 + rng.below(args.len())), vec![target], keys,
         format!("{keys} works from anywhere inside the parentheses."))
}

fn make(kind: &str, r: &mut Rng) -> Option<Made> {
    let semi = |s: &str| format!("{s};");
    Some(match kind {
        "dot-append" => each(r, semi, "A;<Esc>j.j.", "End every line with a semicolon.", "Do one, then j and . for the rest."),
        "dot-prefix" => each(r, |s| format!("- {s}"), "I- <Esc>j.j.", "Start every line with \"- \".", "Do one, then j and . for the rest."),
        "visual-delete" => some(r, 3, (1, 0), "Vjd", "Delete the first two lines.", "V selects whole lines, j grows it, d deletes.", |l| l[2..].to_vec()),
        "visual-indent" => each(r, |s| format!("    {s}"), "Vjj>", "Indent all three lines.", "V, j j, then > pushes them right."),
        "visual-join" => some(r, 3, (1, 0), "VjjJ", "Join all three lines.", "V, j j, then J joins them.", |l| vec![l.join(" ")]),
        "macro-append" => each(r, semi, "qaA;<Esc>jq2@a", "End every line with a semicolon, with a macro.", "qa, the edit and j, q, then 2@a."),
        "macro-quote" => each(r, |s| format!("\"{s}\""), "qaI\"<Esc>A\"<Esc>jq2@a", "Put every line in double quotes, with a macro.", "qa, the edit and j, q, then 2@a."),
        "block-prefix" => each(r, |s| format!("# {s}"), "<C-v>jjI# <Esc>", "Start every line with \"# \".", "Ctrl-v j j, then I types on every line."),
        "block-append" => each(r, semi, "<C-v>jj$A;<Esc>", "End every line with a semicolon.", "$ stretches the block to every line's end; A appends."),
        "move-top" => some(r, 3, (3, 0), ":m0<CR>", "Move the last line to the top.", ":m0 moves this line below line 0.", |l| vec![l[2].clone(), l[0].clone(), l[1].clone()]),
        "copy-end" => some(r, 3, (1, 0), ":t$<CR>", "Copy the first line to the end.", ":t$ copies this line below the last one.", |l| [l, &l[..1]].concat()),
        "range-delete" => some(r, 4, (1, 0), ":2,3d<CR>", "Delete lines 2 and 3 without moving.", "A range in front of d: :2,3d.", |l| vec![l[0].clone(), l[3].clone()]),
        "reverse" => some(r, 3, (1, 0), ":g/^/m0<CR>", "Reverse the lines.", ":g/^/ visits every line; m0 moves each to the top.", |l| l.iter().rev().cloned().collect()),
        "sort" => {
            let mut target = lines(r, 3);
            target.sort();
            let start = target.iter().rev().cloned().collect();
            made("Sort the lines.", start, (1, 0), target, ":sort<CR>", ":sort sorts every line.")
        }
        "norm-append" => each(r, semi, ":%norm A;<CR>", "End every line with a semicolon.", ":%norm runs A; on every line."),
        "sub-prefix" => each(r, |s| format!("- {s}"), ":%s/^/- /<CR>", "Make every line a list item.", "^ matches the start of each line."),
        "comments" => {
            let l = lines(r, 3);
            let start = vec![l[0].clone(), "# cut".into(), l[1].clone(), "# cut".into(), l[2].clone()];
            made("Delete the comment lines.", start, (1, 0), l, ":g/#/d<CR>", ":g runs d on every line that matches #.")
        }
        "sort-u" => {
            let l = lines(r, 2);
            let mut target = l.clone();
            target.sort();
            made("Sort the lines and drop the duplicate.", vec![l[0].clone(), l[1].clone(), l[0].clone()], (1, 0), target, ":sort u<CR>", "u is unique: :sort u keeps one of each.")
        }
        "trailing" => {
            let target = lines(r, 3);
            let start = target.iter().map(|line| format!("{line}{}", " ".repeat(r.between(1, 4)))).collect();
            made("Delete the trailing spaces.", start, (1, 0), target, r":%s/\s\+$//<CR>", r"\s\+$ is one or more spaces right before the end of the line.")
        }
        "delete-to-end" => some(r, 3, (2, 0), "dG", "Delete everything but the first line.", "G goes to the last line, so dG takes it all from here.", |l| l[..1].to_vec()),
        "nav-down" => nav(r, false),
        "nav-up" => nav(r, true),
        "nav-find" => {
            let sentence = r.choice(&with_gaps()).to_string();
            made("Delete the #.", vec![marked(r, &sentence)], (1, 0), vec![sentence], "f#x", "f# lands on it, x crosses it out.")
        }
        "ci-quote" => {
            let pair = r.sample(&MEANINGS, 2);
            let ((key, right), (_, wrong)) = (&pair[0], &pair[1]);
            let start = format!("{key}_means = \"{wrong}\"");
            made(format!("{key} stands for {right}: fix the string."), vec![start.clone()], (1, r.below(start.len() - 1)), vec![format!("{key}_means = \"{right}\"")],
                 format!("ci\"{right}<Esc>"), "ci\" changes what is inside the quotes, and finds them from anywhere before them.")
        }
        "di-paren" => paren(r, false),
        "da-paren" => paren(r, true),
        "di-bracket" => {
            let name = *r.choice(&["keys", "square", "bracket"]);
            let items: Vec<String> = r.sample(&MEANINGS, 3).into_iter().map(|(key, _)| format!("\"{key}\"")).collect();
            let items = items.join(", ");
            made("Empty the list, keeping the square brackets.", vec![format!("{name} = [{items}]")], (1, name.len() + 4 + r.below(items.len())),
                 vec![format!("{name} = []")], "di[", "[ names the square brackets: di[ empties them.")
        }
        "dt-letter" => {
            let filler = format!("{} ", r.sample(&FILLER, 2).join(" "));
            let (sentence, gap) = loop {
                let sentence = r.choice(&SENTENCES);
                let open: Vec<usize> = gaps(sentence).into_iter().filter(|&g| !filler.contains(sentence.as_bytes()[g] as char)).collect();
                if !open.is_empty() {
                    break (sentence, *r.choice(&open));
                }
            };
            let word = sentence[gap..].split(' ').next().unwrap_or("").trim_end_matches(['.', ',', ':', ';']);
            let letter = word.chars().next().unwrap_or('x');
            made(format!("Delete everything up to \"{word}\"."), vec![format!("{}{filler}{}", &sentence[..gap], &sentence[gap..])], (1, gap),
                 vec![sentence.clone()], format!("dt{letter}"), format!("dt{letter} deletes till the next {letter}, and stops just before it."))
        }
        "D-rest" => {
            let sentence = r.choice(&SENTENCES).clone();
            let start = format!("{sentence} {}", r.sample(&FILLER, 3).join(" "));
            made("Delete the filler after the full stop.", vec![start], (1, sentence.len()), vec![sentence], "D", "D is a big d: it deletes to the end of the line.")
        }
        "J-split" => {
            let sentence = r.choice(&with_gaps()).to_string();
            let gap = *r.choice(&gaps(&sentence));
            made("Join the two lines.", vec![sentence[..gap - 1].to_string(), sentence[gap..].to_string()], (1, 0), vec![sentence], "J", "J joins this line and the next, with one space.")
        }
        "ddp-swap" => {
            let l = lines(r, 2);
            made("Swap the two lines.", l.clone(), (1, 0), vec![l[1].clone(), l[0].clone()], "ddp", "dd cuts the line, p puts it below the next one.")
        }
        "count-dw" => {
            let n = r.between(2, 4);
            let sentence = r.choice(&with_gaps()).to_string();
            let gap = *r.choice(&gaps(&sentence));
            let filler: Vec<&str> = (0..n).map(|_| *r.choice(&FILLER)).collect();
            made(format!("Delete the {n} filler words."), vec![format!("{}{} {}", &sentence[..gap], filler.join(" "), &sentence[gap..])], (1, gap),
                 vec![sentence], format!("{n}dw"), format!("A count repeats the verb: {n}dw deletes {n} words."))
        }
        "count-dd" => {
            let n = r.between(2, 4);
            let l = lines(r, 2);
            let mut start = vec![l[0].clone()];
            start.extend((0..n).map(|_| r.choice(&FILLER).to_string()));
            start.push(l[1].clone());
            made(format!("Delete the {n} filler lines."), start, (2, 0), l, format!("{n}dd"), format!("A count works on dd: {n}dd deletes {n} lines."))
        }
        "count-x" => {
            let n = r.between(2, 7);
            let sentence = r.choice(&with_gaps()).to_string();
            let gap = *r.choice(&gaps(&sentence));
            made(format!("Delete the {n} x letters."), vec![format!("{}{}{}", &sentence[..gap], "x".repeat(n), &sentence[gap..])], (1, gap),
                 vec![sentence], format!("{n}x"), format!("x crosses out a character; {n}x crosses out {n}."))
        }
        _ => return None,
    })
}

pub const KINDS: [&str; 37] = [
    "ciw-typo", "daw-double", "ciW-dotted", "dot-append", "dot-prefix", "visual-delete", "visual-indent", "visual-join", "macro-append",
    "macro-quote", "block-prefix", "block-append", "move-top", "copy-end", "range-delete", "reverse", "sort", "norm-append", "sub-prefix",
    "comments", "sort-u", "trailing", "delete-to-end", "nav-down", "nav-up", "nav-find", "ci-quote", "di-paren", "da-paren", "di-bracket",
    "dt-letter", "D-rest", "J-split", "ddp-swap", "count-dw", "count-dd", "count-x",
];

/// The three word-object kinds keep the hint of the task they stand in for.
fn word_task(kind: &str, r: &mut Rng) -> (String, Vec<String>, (usize, usize), Vec<String>, String) {
    let (sentence, spots) = loop {
        let sentence = r.choice(&SENTENCES);
        let found = words(sentence, kind == "ciW-dotted");
        let found: Vec<(usize, usize)> = found.into_iter().filter(|&(start, end)| match kind {
            "daw-double" => sentence.as_bytes()[end] == b' ',
            "ciw-typo" => sentence[start + 1..end - 1].chars().collect::<HashSet<_>>().len() > 1,
            _ => true,
        }).collect();
        if !found.is_empty() {
            break (sentence, found);
        }
    };
    let (start, end) = *r.choice(&spots);
    let (word, before, after) = (&sentence[start..end], &sentence[..start], &sentence[end..]);
    match kind {
        "ciw-typo" => {
            let letters: Vec<char> = word.chars().collect();
            let i = loop {
                let i = r.between(1, letters.len() - 3);
                if letters[i] != letters[i + 1] {
                    break i;
                }
            };
            let mut swapped = letters.clone();
            swapped.swap(i, i + 1);
            let shown: String = swapped.into_iter().collect();
            let cursor = before.len() + r.below(shown.len());
            (format!("Fix \"{shown}\" to \"{word}\"."), vec![format!("{before}{shown}{after}")], (1, cursor), vec![sentence.clone()], format!("ciw{word}<Esc>"))
        }
        "daw-double" => {
            let which = if r.coin() { 0 } else { word.len() + 1 };
            let cursor = before.len() + which + r.below(word.len());
            (format!("Delete the doubled \"{word}\"."), vec![format!("{before}{word} {word}{after}")], (1, cursor), vec![sentence.clone()], "daw".into())
        }
        _ => {
            let shown = word.chars().map(String::from).collect::<Vec<_>>().join(".");
            let cursor = before.len() + r.below(shown.len());
            (format!("Write the dotted \"{shown}\" as \"{word}\"."), vec![format!("{before}{shown}{after}")], (1, cursor), vec![sentence.clone()], format!("ciW{word}<Esc>"))
        }
    }
}

/// A `kind` task from `seed`, with the parent task's place in its lesson.
pub fn generate(kind: &str, seed: &str, parent: &Task) -> Task {
    let mut rng = Rng::new(&format!("{kind}:{seed}"));
    let base = Task { ft: String::new(), generated: seed.to_string(), ..parent.clone() };
    if matches!(kind, "ciw-typo" | "daw-double" | "ciW-dotted") {
        let (goal, start, cursor, target, solution) = word_task(kind, &mut rng);
        return Task { goal, start, cursor, target, solution, ..base };
    }
    let m = make(kind, &mut rng).unwrap_or_else(|| panic!("no generator called {kind}"));
    Task { goal: m.goal, start: m.start, cursor: m.cursor, target: m.target, solution: m.solution, hint: m.hint, ..base }
}
