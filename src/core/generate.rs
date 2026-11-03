//! Practice texts made from a seed, so a skill is practised on text you haven't seen.
//!
//! A lesson task names a `generate` kind. Its Learn round keeps the written text (about
//! its own keys, to teach them); Recall, reviews, Endless and Quick practice get a new
//! one each time. The text comes from corpus.rs: sentences from linguistics books and
//! names made of linguistics terms. The same seed always gives the same task, and
//! tests/check_neovim.py types every kind's solution into a real Neovim.

use super::corpus::{self, capitalised, gaps, names, ordinal, shortest_search, spans, whole};
use super::lessons::Task;
use std::collections::HashSet;

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
const HEDGES: [&str; 6] = ["well, you know, ", "so, um, ", "basically, sort of, ", "honestly, in a way, ", "um, more or less, ", "like, kind of, "];
const BOX: usize = 70; // the widest line the practice box shows whole

struct Made {
    goal: String,
    start: Vec<String>,
    cursor: (usize, usize),
    target: Vec<String>,
    solution: String,
    hint: String,
}

fn made(goal: impl Into<String>, start: Vec<String>, cursor: (usize, usize), target: Vec<String>, solution: impl Into<String>, hint: impl Into<String>) -> Made {
    Made { goal: goal.into(), start, cursor, target, solution: solution.into(), hint: hint.into() }
}

/// A line with something `pick` can use, and the thing it picked.
fn line_with<T: Clone>(r: &mut Rng, pick: impl Fn(&str) -> Vec<T>) -> (String, T) {
    loop {
        let line = corpus::roomy(r);
        let found = pick(&line);
        if !found.is_empty() {
            let item = r.choice(&found).clone();
            return (line, item);
        }
    }
}

/// Letters i and i+1 of `word` swapped, at a place where that changes it.
fn typo(r: &mut Rng, word: &str) -> Option<String> {
    let letters: Vec<char> = word.chars().collect();
    let spots: Vec<usize> = (1..letters.len().saturating_sub(2)).filter(|&i| letters[i] != letters[i + 1]).collect();
    if spots.is_empty() {
        return None;
    }
    let i = *r.choice(&spots);
    let mut swapped = letters;
    swapped.swap(i, i + 1);
    Some(swapped.into_iter().collect())
}

/// `word` swapped for `new` wherever it stands alone, as `*` would find it.
fn replace_whole(line: &str, word: &str, new: &str) -> String {
    let mut out = line.to_string();
    for at in whole(line, word).into_iter().rev() {
        out.replace_range(at..at + word.len(), new);
    }
    out
}

/// A corpus word that isn't `not`.
fn other_word(r: &mut Rng, not: &str) -> String {
    loop {
        let word = corpus::word(r);
        if word != not {
            return word;
        }
    }
}

fn insert(line: &str, at: usize, text: &str) -> String {
    format!("{}{text}{}", &line[..at], &line[at..])
}

/// `word ` put in front of a word of each line; None when a line has no room.
fn insert_each(r: &mut Rng, lines: &[String], word: &str) -> Option<(Vec<String>, Vec<usize>)> {
    let mut out = Vec::new();
    let mut at = Vec::new();
    for line in lines {
        let spots = gaps(line);
        if spots.is_empty() || line.len() + word.len() + 1 > BOX {
            return None;
        }
        let gap = *r.choice(&spots);
        out.push(insert(line, gap, &format!("{word} ")));
        at.push(gap);
    }
    Some((out, at))
}

/// Lines `word` doesn't appear in yet, so `*` and `/` find only what we put there.
fn lines_without(r: &mut Rng, n: usize, word: &str) -> Vec<String> {
    loop {
        let lines = corpus::roomy_lines(r, n);
        if !lines.iter().any(|l| l.to_lowercase().contains(&word.to_lowercase())) {
            return lines;
        }
    }
}

fn each(r: &mut Rng, change: impl Fn(&str) -> String, keys: &str, goal: &str, hint: &str) -> Made {
    let start = corpus::roomy_lines(r, 3);
    let target = start.iter().map(|line| change(line)).collect();
    made(goal, start, (1, 0), target, keys, hint)
}

fn some(r: &mut Rng, n: usize, cursor: (usize, usize), keys: &str, goal: &str, hint: &str, target: impl Fn(&[String]) -> Vec<String>) -> Made {
    let start = corpus::roomy_lines(r, n);
    let target = target(&start);
    made(goal, start, cursor, target, keys, hint)
}

fn marked(r: &mut Rng, line: &str) -> String {
    let gap = *r.choice(&gaps(line));
    insert(line, gap, "#")
}

fn nav(r: &mut Rng, up: bool) -> Made {
    let n = r.between(4, 11);
    let target = corpus::roomy_lines(r, n + 1);
    let (far, near) = if up { (0, n) } else { (n, 0) };
    let mut start = target.clone();
    start[far] = marked(r, &target[far]);
    let key = if up { 'k' } else { 'j' };
    made("Delete the #.", start, (near + 1, 0), target, format!("{n}{key}f#x"), format!("The line numbers say how far: {n}{key}, then f# and x."))
}

fn paren(r: &mut Rng, around: bool) -> Made {
    let n = names(r, 4);
    let args = n[1..].join(", ");
    let (target, keys, what) = if around {
        (format!("{} + 1", n[0]), "da(", "the call's parentheses and arguments")
    } else {
        (format!("{}() + 1", n[0]), "di(", "the arguments, keeping the parentheses")
    };
    made(format!("Delete {what}."), vec![format!("{}({args}) + 1", n[0])], (1, n[0].len() + 1 + r.below(args.len())), vec![target], keys,
         format!("{keys} works from anywhere inside the parentheses."))
}

/// Names for a `ct` task: the last, typed after `ct;`, mustn't start with "an" or "in",
/// Neovim 0.12's operator-pending node selections, which typed-ahead keys can run into.
fn ct_names(r: &mut Rng, n: usize) -> Vec<String> {
    loop {
        let found = names(r, n);
        if !found[n - 1].starts_with("an") && !found[n - 1].starts_with("in") {
            return found;
        }
    }
}

/// A code line around one name: (before, after).
fn code_around(r: &mut Rng, other: &[String]) -> (String, String) {
    match r.below(4) {
        0 => ("def ".into(), format!("({}, {}):", other[0], other[1])),
        1 => (format!("{} = ", other[0]), format!("({})", other[1])),
        2 => ("return ".into(), format!("({}, {})", other[0], other[1])),
        _ => (String::new(), format!(" = {}({})", other[0], other[1])),
    }
}

/// A list line: "Stems, roots, vowels, tones, and clauses."
fn listing(r: &mut Rng) -> String {
    let w = corpus::words(r, 5);
    format!("{}, {}, {}, {}, and {}.", capitalised(&w[0]), w[1], w[2], w[3], w[4])
}

fn nth_comma(line: &str, n: usize) -> usize {
    line.match_indices(',').nth(n - 1).map(|(i, _)| i).expect("enough commas")
}

/// Three sentences on a line, and where the middle one starts.
fn three_sentences(r: &mut Rng) -> (Vec<String>, String, usize) {
    let s = corpus::short(r, 4);
    (s.clone(), format!("{} {} {}", s[0], s[1], s[2]), s[0].len() + 1)
}

/// Paragraphs of one or two lines.
fn paragraph(r: &mut Rng) -> Vec<String> {
    let n = r.between(1, 2);
    corpus::roomy_lines(r, n)
}

fn sum(r: &mut Rng, op: &str, n: usize, keys: String, goal: String) -> Made {
    let a = r.between(n + 2, 60);
    let label = capitalised(&corpus::term(r));
    let start = format!("{label}: {a} {op} {n} = {a}");
    let result = if op == "+" { a + n } else { a - n };
    let target = format!("{label}: {a} {op} {n} = {result}");
    let hint = if op == "+" { "Ctrl-a adds to the number under or after the cursor; a count adds that many." } else { "Ctrl-x takes away from the number under or after the cursor." };
    made(goal, vec![start.clone()], (1, start.find('=').expect("an equals sign")), vec![target], keys, hint)
}

fn make(kind: &str, r: &mut Rng) -> Option<Made> {
    let semi = |s: &str| format!("{s};");
    Some(match kind {
        // week 3 and 4
        "dot-append" => each(r, semi, "A;<Esc>j.j.", "End every line with a semicolon.", "Do one, then j and . for the rest."),
        "dot-prefix" => each(r, |s| format!("- {s}"), "I- <Esc>j.j.", "Start every line with \"- \".", "Do one, then j and . for the rest."),
        "visual-delete" => some(r, 3, (1, 0), "Vjd", "Delete the first two lines.", "V selects whole lines, j grows it, d deletes.", |l| l[2..].to_vec()),
        "visual-indent" => each(r, |s| format!("    {s}"), "Vjj>", "Indent all three lines.", "V, j j, then > pushes them right."),
        "visual-join" => {
            let l = corpus::short(r, 3);
            made("Join all three lines.", l.clone(), (1, 0), vec![l.join(" ")], "VjjJ", "V, j j, then J joins them.")
        }
        "macro-append" => each(r, semi, "qaA;<Esc>jq2@a", "End every line with a semicolon, with a macro.", "qa, the edit and j, q, then 2@a."),
        "macro-quote" => each(r, |s| format!("\"{s}\""), "qaI\"<Esc>A\"<Esc>jq2@a", "Put every line in double quotes, with a macro.", "qa, the edit and j, q, then 2@a."),
        "block-prefix" => each(r, |s| format!("# {s}"), "<C-v>jjI# <Esc>", "Start every line with \"# \".", "Ctrl-v j j, then I types on every line."),
        "block-append" => each(r, semi, "<C-v>jj$A;<Esc>", "End every line with a semicolon.", "$ stretches the block to every line's end; A appends."),
        "move-top" => some(r, 3, (3, 0), ":m0<CR>", "Move the last line to the top.", ":m0 moves this line below line 0.", |l| vec![l[2].clone(), l[0].clone(), l[1].clone()]),
        "copy-end" => some(r, 3, (1, 0), ":t$<CR>", "Copy the first line to the end.", ":t$ copies this line below the last one.", |l| [l, &l[..1]].concat()),
        "range-delete" => some(r, 4, (1, 0), ":2,3d<CR>", "Delete lines 2 and 3 without moving.", "A range in front of d: :2,3d.", |l| vec![l[0].clone(), l[3].clone()]),
        "reverse" => some(r, 3, (1, 0), ":g/^/m0<CR>", "Reverse the lines.", ":g/^/ visits every line; m0 moves each to the top.", |l| l.iter().rev().cloned().collect()),
        "sort" => {
            let mut target = corpus::roomy_lines(r, 3);
            target.sort();
            let start = target.iter().rev().cloned().collect();
            made("Sort the lines.", start, (1, 0), target, ":sort<CR>", ":sort sorts every line.")
        }
        "norm-append" => each(r, semi, ":%norm A;<CR>", "End every line with a semicolon.", ":%norm runs A; on every line."),
        "sub-prefix" => each(r, |s| format!("- {s}"), ":%s/^/- /<CR>", "Make every line a list item.", "^ matches the start of each line."),
        "comments" => {
            let l = corpus::roomy_lines(r, 3);
            let start = vec![l[0].clone(), "# cut".into(), l[1].clone(), "# cut".into(), l[2].clone()];
            made("Delete the comment lines.", start, (1, 0), l, ":g/#/d<CR>", ":g runs d on every line that matches #.")
        }
        "sort-u" => {
            let l = corpus::roomy_lines(r, 2);
            let mut target = l.clone();
            target.sort();
            made("Sort the lines and drop the duplicate.", vec![l[0].clone(), l[1].clone(), l[0].clone()], (1, 0), target, ":sort u<CR>", "u is unique: :sort u keeps one of each.")
        }
        "trailing" => {
            let target = corpus::roomy_lines(r, 3);
            let start = target.iter().map(|line| format!("{line}{}", " ".repeat(r.between(1, 4)))).collect();
            made("Delete the trailing spaces.", start, (1, 0), target, r":%s/\s\+$//<CR>", r"\s\+$ is one or more spaces right before the end of the line.")
        }
        "delete-to-end" => some(r, 3, (2, 0), "dG", "Delete everything but the first line.", "G goes to the last line, so dG takes it all from here.", |l| l[..1].to_vec()),
        "nav-down" => nav(r, false),
        "nav-up" => nav(r, true),
        "nav-find" => {
            let line = corpus::roomy(r);
            made("Delete the #.", vec![marked(r, &line)], (1, 0), vec![line], "f#x", "f# lands on it, x crosses it out.")
        }

        // week 1, day 1: words
        "ciw-ident" => {
            let n = names(r, 4);
            let (old, new) = (&n[0], &n[1]);
            let (before, after) = code_around(r, &n[2..]);
            made(format!("Rename {old} to {new}."), vec![format!("{before}{old}{after}")], (1, before.len() + r.below(old.len())),
                 vec![format!("{before}{new}{after}")], format!("ciw{new}<Esc>"), "Underscores belong to the word: ciw takes the whole name.")
        }
        "ciw-url" => {
            let t = corpus::terms(r, 4);
            let start = format!("https://{}.{}.org/{}", t[0], t[1], t[2]);
            made(format!("Change the subdomain to {}.", t[3]), vec![start], (1, 8 + r.below(t[0].len())), vec![format!("https://{}.{}.org/{}", t[3], t[1], t[2])],
                 format!("ciw{}<Esc>", t[3]), "Dots and slashes end a word, so ciw takes just the subdomain.")
        }
        "copy-over" => {
            let (line, (a, b)) = loop {
                let line = corpus::roomy(r).trim_end_matches('.').to_string();
                let s = spans(&line);
                let last = &line[s.last().expect("words").0..];
                let options: Vec<(usize, usize)> = s[..s.len() - 1].iter().copied().filter(|&(a, b)| b - a >= 3 && &line[a..b] != last).collect();
                if !options.is_empty() {
                    let pick = *r.choice(&options);
                    break (line, pick);
                }
            };
            let b_start = spans(&line).last().expect("words").0;
            let last = line[b_start..].to_string();
            let word = line[a..b].to_string();
            made(format!("Copy \"{word}\" over \"{last}\", the last word."), vec![line.clone()], (1, a + r.below(b - a)), vec![format!("{}{word}", &line[..b_start])],
                 "yiw$viwp", "yiw copies the word, $ goes to the last one, viwp puts the copy over it.")
        }

        // week 1, day 2: pairs
        "ci-quote" => {
            let n = names(r, 1);
            let w = corpus::words(r, 4);
            let (old, new) = (format!("{} {}", w[0], w[1]), format!("{} {}", w[2], w[3]));
            let start = format!("{} = \"{old}\"", n[0]);
            made(format!("Set the string to \"{new}\"."), vec![start.clone()], (1, r.below(start.len() - 1)), vec![format!("{} = \"{new}\"", n[0])],
                 format!("ci\"{new}<Esc>"), "ci\" changes what is inside the quotes, and finds them from anywhere before them.")
        }
        "di-paren" => paren(r, false),
        "da-paren" => paren(r, true),
        "di-bracket" => {
            let n = names(r, 1);
            let items = corpus::terms(r, 3).iter().map(|t| format!("\"{t}\"")).collect::<Vec<_>>().join(", ");
            made("Empty the list, keeping the square brackets.", vec![format!("{} = [{items}]", n[0])], (1, n[0].len() + 4 + r.below(items.len())),
                 vec![format!("{} = []", n[0])], "di[", "[ names the square brackets: di[ empties them.")
        }
        "ci-paren" => {
            let n = names(r, 5);
            let start = format!("{}({}, {}, {})", n[0], n[1], n[2], n[3]);
            made(format!("Replace all the arguments with {}.", n[4]), vec![start], (1, n[0].len() + 1 + r.below(n[1].len() + n[2].len() + n[3].len() + 4)),
                 vec![format!("{}({})", n[0], n[4])], format!("ci({}<Esc>", n[4]), "ci( changes everything between the parentheses.")
        }
        "cit-tag" => {
            let tag = *r.choice(&["p", "em", "li", "b", "h2", "span"]);
            let s = corpus::short(r, 2);
            let open = format!("<{tag}>");
            made(format!("Change the text inside the tag to \"{}\".", s[1]), vec![format!("{open}{}</{tag}>", s[0])], (1, open.len() + r.below(s[0].len())),
                 vec![format!("{open}{}</{tag}>", s[1])], format!("cit{}<Esc>", s[1]), "t is a tag: cit changes what is between <tag> and </tag>.")
        }

        // week 1, day 3: sentences and paragraphs
        "dap-middle" => {
            let (a, b, c) = (paragraph(r), paragraph(r), paragraph(r));
            let start = [a.clone(), vec![String::new()], b.clone(), vec![String::new()], c.clone()].concat();
            let row = a.len() + 2 + r.below(b.len());
            let col = r.below(start[row - 1].len());
            made("Delete the middle paragraph.", start, (row, col), [a, vec![String::new()], c].concat(), "dap", "ap is a paragraph and the blank line after it.")
        }
        "yap-dup" => {
            let a = corpus::roomy_lines(r, 2);
            let b = paragraph(r);
            let start = [a.clone(), vec![String::new()], b.clone()].concat();
            let row = 1 + r.below(2);
            made("Duplicate the first paragraph.", start, (row, r.below(a[row - 1].len())), [a.clone(), vec![String::new()], a, vec![String::new()], b].concat(),
                 "yapP", "yap copies the paragraph with its blank line; P puts it above.")
        }
        "cis-sentence" => {
            let (s, line, at) = three_sentences(r);
            made(format!("Change the middle sentence to \"{}\"", s[3]), vec![line], (1, at + r.below(s[1].len())), vec![format!("{} {} {}", s[0], s[3], s[2])],
                 format!("cis{}<Esc>", s[3]), "A sentence ends at a full stop: cis changes the one the cursor is in.")
        }
        "das-middle" => {
            let (s, line, at) = three_sentences(r);
            made("Delete the middle sentence.", vec![line], (1, at + r.below(s[1].len())), vec![format!("{} {}", s[0], s[2])],
                 "das", "as is a sentence and the space after it.")
        }
        "ip-indent" => {
            let mut p = corpus::roomy_lines(r, 4);
            let after = p.pop().expect("four lines");
            let row = 1 + r.below(3);
            let start = [p.clone(), vec![String::new(), after.clone()]].concat();
            let target = [p.iter().map(|l| format!("    {l}")).collect(), vec![String::new(), after]].concat();
            made("Indent the paragraph.", start, (row, r.below(p[row - 1].len())), target, ">ip", "> is an operator too: >ip indents the paragraph.")
        }

        // week 1, day 4: find and till
        "dt-letter" => {
            let filler = format!("{} ", r.sample(&FILLER, 2).join(" "));
            let (line, gap) = line_with(r, |l| gaps(l).into_iter().filter(|&g| !filler.contains(l.as_bytes()[g] as char)).collect());
            let word = line[gap..].split([' ', ',', '.']).next().unwrap_or("").to_string();
            let letter = word.chars().next().unwrap_or('x');
            made(format!("Delete everything up to \"{word}\"."), vec![insert(&line, gap, &filler)], (1, gap), vec![line.clone()],
                 format!("dt{letter}"), format!("dt{letter} deletes till the next {letter}, and stops just before it."))
        }
        "ct-semi" => {
            let n = ct_names(r, 4);
            let before = format!("let {} = ", n[0]);
            let old = format!("{}({})", n[1], n[2]);
            made(format!("Change the value to {} (keep the semicolon).", n[3]), vec![format!("{before}{old};")], (1, before.len()), vec![format!("{before}{};", n[3])],
                 format!("ct;{}<Esc>", n[3]), "ct; changes till the semicolon and leaves it.")
        }
        "path-T" => {
            let t = corpus::terms(r, 4);
            let ext = *r.choice(&["txt", "md", "py", "csv"]);
            let folders = format!("/{}/{}/", t[0], t[1]);
            let file = format!("{}_{}.{ext}", t[2], t[3]);
            made("Keep the folders: delete the file name.", vec![format!("{folders}{file}")], (1, folders.len() + 1 + r.below(file.len() - 1)), vec![folders],
                 "T/D", "T/ goes back till the slash, D deletes from there to the end.")
        }
        "nf-comma" => {
            let line = listing(r);
            let n = r.between(2, 4);
            let at = nth_comma(&line, n);
            made(format!("Turn the {} comma into a semicolon.", ordinal(n)), vec![line.clone()], (1, 0), vec![format!("{};{}", &line[..at], &line[at + 1..])],
                 format!("{n}f,r;"), format!("A count works on f: {n}f, lands on the {} comma.", ordinal(n)))
        }
        "ct-space" => {
            let n = ct_names(r, 5);
            let before = format!("{} = ", n[0]);
            let call = format!("{}({})", n[1], n[2]);
            made(format!("Replace the whole {call} call with {}.", n[4]), vec![format!("{before}{call} + {}", n[3])], (1, before.len()),
                 vec![format!("{before}{} + {}", n[4], n[3])], format!("ct {}<Esc>", n[4]), "ct and a space changes till the next space.")
        }
        "df-paren" => {
            let aside = corpus::words(r, 2).join(" ");
            let (line, gap) = line_with(r, |l| if l.len() + aside.len() + 3 > BOX { Vec::new() } else { gaps(l) });
            let space = gap - 1;
            made("Delete the space and the part in brackets.", vec![insert(&line, space, &format!(" ({aside})"))], (1, space), vec![line.clone()],
                 "df)", "df) deletes up to and including the closing bracket.")
        }

        // week 1, day 5: lines
        "D-rest" => {
            let line = corpus::roomy(r);
            let start = format!("{line} {}", r.sample(&FILLER, 3).join(" "));
            made("Delete the filler after the full stop.", vec![start], (1, line.len()), vec![line], "D", "D is a big d: it deletes to the end of the line.")
        }
        "C-rest" => {
            let (line, gap) = line_with(r, gaps);
            let new = corpus::short(r, 1)[0].to_lowercase();
            made(format!("Change the rest of the line to \"{new}\""), vec![line.clone()], (1, gap), vec![format!("{}{new}", &line[..gap])],
                 format!("C{new}<Esc>"), "C is a big c: it changes to the end of the line.")
        }
        "cc-line" => {
            let l = corpus::roomy_lines(r, 3);
            let new = corpus::short(r, 1).remove(0);
            made(format!("Replace the middle line with \"{new}\""), l.clone(), (2, r.below(l[1].len())), vec![l[0].clone(), new.clone(), l[2].clone()],
                 format!("cc{new}<Esc>"), "cc changes the whole line, wherever the cursor is.")
        }
        "J-split" => {
            let (line, gap) = line_with(r, gaps);
            made("Join the two lines.", vec![line[..gap - 1].to_string(), line[gap..].to_string()], (1, 0), vec![line.clone()], "J", "J joins this line and the next, with one space.")
        }
        "ddp-swap" => {
            let l = corpus::roomy_lines(r, 2);
            made("Swap the two lines.", l.clone(), (1, 0), vec![l[1].clone(), l[0].clone()], "ddp", "dd cuts the line, p puts it below the next one.")
        }
        "A-semicolon" => {
            let n = names(r, 4);
            let line = format!("let {} = {}({}, {})", n[0], n[1], n[2], n[3]);
            made("End the line with a semicolon.", vec![line.clone()], (1, r.below(line.len())), vec![format!("{line};")], "A;<Esc>", "A appends at the end of the line, wherever the cursor is.")
        }
        "I-comment" => {
            let n = names(r, 3);
            let line = if r.coin() { format!("    return {}({})", n[0], n[1]) } else { format!("    {} = {}({})", n[0], n[1], n[2]) };
            made("Comment the line out with \"# \".", vec![line.clone()], (1, r.below(line.len())), vec![format!("    # {}", line.trim_start())],
                 "I# <Esc>", "I inserts before the first character that isn't a space.")
        }

        // week 1, day 6: counts
        "count-dw" => {
            let n = r.between(2, 4);
            let (line, gap) = line_with(r, gaps);
            let filler: Vec<&str> = (0..n).map(|_| *r.choice(&FILLER)).collect();
            made(format!("Delete the {n} filler words."), vec![insert(&line, gap, &format!("{} ", filler.join(" ")))], (1, gap),
                 vec![line.clone()], format!("{n}dw"), format!("A count repeats the verb: {n}dw deletes {n} words."))
        }
        "count-dd" => {
            let n = r.between(2, 4);
            let l = corpus::roomy_lines(r, n + 2);
            let row = r.below(2) + 1;
            let target = [&l[..row], &l[row + n..]].concat();
            made(format!("Delete the {n} lines from the cursor down."), l, (row + 1, 0), target, format!("{n}dd"), format!("A count works on dd: {n}dd deletes {n} lines."))
        }
        "count-x" => {
            let n = r.between(2, 7);
            let (line, gap) = line_with(r, gaps);
            made(format!("Delete the {n} x letters."), vec![insert(&line, gap, &"x".repeat(n))], (1, gap),
                 vec![line.clone()], format!("{n}x"), format!("x crosses out a character; {n}x crosses out {n}."))
        }
        "count-cw" => {
            let (line, first) = line_with(r, |l| {
                let s = spans(l);
                (0..s.len().saturating_sub(1)).filter(|&i| s[i].1 + 1 == s[i + 1].0 && l.as_bytes()[s[i].1] == b' ' && l.as_bytes().get(s[i + 1].1) != Some(&b',')).map(|i| (s[i].0, s[i + 1].1)).collect()
            });
            let new = corpus::words(r, 2).join(" ");
            let old = &line[first.0..first.1];
            made(format!("Change \"{old}\" to \"{new}\"."), vec![line.clone()], (1, first.0), vec![format!("{}{new}{}", &line[..first.0], &line[first.1..])],
                 format!("c2w{new}<Esc>"), "A count works on cw too: c2w changes two words.")
        }
        "nf-D" => {
            let line = listing(r);
            let n = r.between(2, 4);
            let at = nth_comma(&line, n);
            made(format!("Delete from the {} comma to the end of the line.", ordinal(n)), vec![line.clone()], (1, 0), vec![line[..at].to_string()],
                 format!("{n}f,D"), format!("{n}f, lands on the {} comma, D deletes from there.", ordinal(n)))
        }
        "count-J" => {
            let (n, mid) = loop {
                let n = r.between(3, 4);
                let mid = corpus::short(r, n);
                if mid.iter().map(|s| s.len() + 1).sum::<usize>() <= BOX + 1 {
                    break (n, mid);
                }
            };
            let around = corpus::roomy_lines(r, 2);
            let start = [vec![around[0].clone()], mid.clone(), vec![around[1].clone()]].concat();
            made(format!("Join the {n} short lines into one."), start, (2, 0), vec![around[0].clone(), mid.join(" "), around[1].clone()],
                 format!("{n}J"), format!("{n}J joins {n} lines, starting with this one."))
        }
        "count-jdd" => {
            let n = r.between(2, 6);
            let l = corpus::roomy_lines(r, n + 2);
            let target = l.iter().enumerate().filter(|&(i, _)| i != n).map(|(_, s)| s.clone()).collect();
            made(format!("Delete the line {n} lines below the cursor."), l, (1, 0), target, format!("{n}jdd"), format!("The relative numbers say how far: {n}j, then dd."))
        }
        "count-kciw" => {
            let n = r.between(2, 5);
            let (mut l, word, wrong) = loop {
                let l = corpus::roomy_lines(r, n + 1);
                let word = l[0][..spans(&l[0])[0].1].to_string();
                if word.len() >= 4
                    && let Some(wrong) = typo(r, &word)
                {
                    break (l, word, wrong);
                }
            };
            let target = l.clone();
            l[0] = format!("{wrong}{}", &l[0][word.len()..]);
            made(format!("Fix \"{wrong}\", {n} lines up."), l, (n + 1, 0), target, format!("{n}kciw{word}<Esc>"), format!("{n}k goes up {n} lines; ciw fixes the word."))
        }

        // week 1, day 7: review
        "indent-body" => {
            let n = names(r, 4);
            let start = vec![format!("def {}({}):", n[0], n[1]), format!("{} = {}({})", n[2], n[3], n[1]), format!("return {}", n[2])];
            let mut target = start.clone();
            target[1] = format!("    {}", start[1]);
            target[2] = format!("    {}", start[2]);
            made("Indent the body of the function.", start, (2, 0), target, ">j", "> takes a motion like d does: >j indents this line and the next.")
        }

        // week 2, day 1: the dot
        "dot-ciw" => {
            let (line, i) = line_with(r, |l| {
                let s = spans(l);
                let b = l.as_bytes();
                (0..s.len().saturating_sub(2)).filter(|&i| s[i].1 + 1 == s[i + 1].0 && s[i + 1].1 + 1 == s[i + 2].0 && b[s[i].1] == b' ' && b[s[i + 1].1] == b' ').collect()
            });
            let s = spans(&line);
            let w = corpus::words(r, 2);
            let (old, new) = (&w[0], &w[1]);
            let build = |word: &str| format!("{}{word} {} {word}{}", &line[..s[i].0], &line[s[i + 1].0..s[i + 1].1], &line[s[i + 2].1..]);
            made(format!("Change both \"{old}\" to \"{new}\"."), vec![build(old)], (1, s[i].0 + r.below(old.len())), vec![build(new)],
                 format!("ciw{new}<Esc>ww."), "Change one, move to the other, and . does the same change again.")
        }
        "dot-indent" => some(r, 3, (1, 0), ">>j.", "Indent the first two lines.", ">> indents a line; j and . do the next.", |l| vec![format!("    {}", l[0]), format!("    {}", l[1]), l[2].clone()]),
        "dot-dw" => {
            let word = corpus::word(r);
            let (line, gap) = line_with(r, gaps);
            made(format!("Delete all three \"{word}\"."), vec![insert(&line, gap, &format!("{word} ").repeat(3))], (1, gap), vec![line.clone()],
                 "dw..", "dw deletes one; . repeats it.")
        }
        "dot-comment" => {
            let n = names(r, 5);
            let start = vec![format!("{} = {}({})", n[0], n[1], n[2]), format!("{}({})", n[3], n[0]), format!("return {}", n[4])];
            let target = start.iter().map(|l| format!("# {l}")).collect();
            made("Comment out all three lines with \"# \".", start, (1, 0), target, "I# <Esc>j.j.", "Do one with I, then j and . for the rest.")
        }

        // week 2, day 2: searching
        "search-cw" => {
            let (line, (at, end, pattern)) = line_with(r, |l| {
                spans(l).into_iter().filter(|&(a, b)| a >= 12 && b - a >= 3 && l[a..b].chars().all(|c| c.is_ascii_lowercase()))
                    .filter_map(|(a, b)| shortest_search(l, 0, a, &l[a..b], true).map(|p| (a, b, p))).collect()
            });
            let old = line[at..end].to_string();
            let new = other_word(r, &old);
            made(format!("Change \"{old}\" to \"{new}\"."), vec![line.clone()], (1, 0), vec![format!("{}{new}{}", &line[..at], &line[end..])],
                 format!("/{pattern}<CR>cw{new}<Esc>"), "Search for the word's first letters, then cw. The fewer letters that find it, the better.")
        }
        "search-d" => {
            let hedge = *r.choice(&HEDGES);
            let (line, pattern) = line_with(r, |l| {
                let start = format!("{hedge}{l}");
                let first = &l[..spans(l)[0].1];
                shortest_search(&start, 0, hedge.len(), first, true).into_iter().collect()
            });
            let first = &line[..spans(&line)[0].1];
            made(format!("Delete the hedging before \"{first}\"."), vec![format!("{hedge}{line}")], (1, 0), vec![line.clone()],
                 format!("d/{pattern}<CR>"), "A search is a motion: d/ deletes up to what it finds.")
        }
        "star-ciw" => {
            let n = names(r, 5);
            let start = vec![format!("{} = {}({})", n[0], n[1], n[2]), format!("{}({}, {})", n[3], n[0], n[2])];
            let target = vec![start[0].clone(), format!("{}({}, {})", n[3], n[4], n[2])];
            made(format!("Rename the second {} to {}.", n[0], n[4]), start, (1, r.below(n[0].len())), target, format!("*ciw{}<Esc>", n[4]),
                 "* jumps to the next place the word under the cursor appears.")
        }
        "star-n-daw" => {
            let word = corpus::word(r);
            let (plain, start, at) = loop {
                let plain = lines_without(r, 3, &word);
                if let Some((start, at)) = insert_each(r, &plain, &word) {
                    break (plain, start, at);
                }
            };
            let target = vec![start[0].clone(), start[1].clone(), plain[2].clone()];
            made(format!("Delete the third \"{word}\"."), start, (1, at[0] + r.below(word.len())), target, "*ndaw", "* finds the next one, n the one after, daw deletes it.")
        }
        "search-back" => {
            let word = corpus::word(r);
            let (plain, start, at, pattern) = loop {
                let plain = lines_without(r, 2, &word);
                let Some((start, at)) = insert_each(r, &plain, &word) else { continue };
                let text = start.join("\n");
                let cursor = start[0].len() + 1 + start[1].len() - 1;
                if let Some(pattern) = shortest_search(&text, cursor, start[0].len() + 1 + at[1], &word, false) {
                    break (plain, start, at, pattern);
                }
            };
            let new = other_word(r, &word);
            let target = vec![start[0].clone(), insert(&plain[1], at[1], &format!("{new} "))];
            made(format!("Change the last \"{word}\" to \"{new}\", searching backwards."), start.clone(), (2, start[1].len() - 1), target,
                 format!("?{pattern}<CR>cw{new}<Esc>"), "? searches backwards, to the nearest one behind the cursor.")
        }

        // week 2, day 3: cgn
        "cgn-star3" => {
            let n = names(r, 5);
            let x = &n[0];
            let start = vec![format!("{x} = {}({})", n[1], n[2]), format!("{}({x})", n[3]), format!("return {x}")];
            let target = start.iter().map(|l| replace_whole(l, x, &n[4])).collect();
            made(format!("Rename every {x} to {}.", n[4]), start, (1, r.below(x.len())), target, format!("*cgn{}<Esc>..", n[4]),
                 "* sets the search, cgn changes the next match, . does the next one.")
        }
        "cgn-star4" => {
            let w = corpus::words(r, 2);
            let (old, new) = (&w[0], &w[1]);
            let (start, target, first) = loop {
                let plain = lines_without(r, 2, old);
                let Some((once, _)) = insert_each(r, &plain, old) else { continue };
                let Some((twice, _)) = insert_each(r, &once, old) else { continue };
                let target: Vec<String> = twice.iter().map(|l| replace_whole(l, old, new)).collect();
                let first = whole(&twice[0], old)[0];
                break (twice, target, first);
            };
            made(format!("Change all four \"{old}\" to \"{new}\"."), start, (1, first + r.below(old.len())), target, format!("*cgn{new}<Esc>..."),
                 "cgn changes the next match; each . changes one more.")
        }
        "cgn-skip" => {
            let w = corpus::words(r, 2);
            let (old, new) = (&w[0], &w[1]);
            let (plain, start, at) = loop {
                let plain = lines_without(r, 3, old);
                if let Some((start, at)) = insert_each(r, &plain, old) {
                    break (plain, start, at);
                }
            };
            let target = vec![insert(&plain[0], at[0], &format!("{new} ")), start[1].clone(), insert(&plain[2], at[2], &format!("{new} "))];
            made(format!("Change the first and the last \"{old}\" to \"{new}\", and keep the middle one."), start, (1, at[0] + r.below(old.len())), target,
                 format!("*Ncgn{new}<Esc>nn."), "n skips a match you want to keep; . changes the one you're on.")
        }
        "cgn-phrase" => {
            let w = corpus::words(r, 4);
            let (old, new) = (format!("{} {}", w[0], w[1]), format!("{} {}", w[2], w[3]));
            let (plain, start, at) = loop {
                let plain = lines_without(r, 2, &old);
                if let Some((start, at)) = insert_each(r, &plain, &old)
                    && start.join("\n").to_lowercase().matches(&old).count() == 2
                {
                    break (plain, start, at);
                }
            };
            let target = plain.iter().zip(&at).map(|(l, &a)| insert(l, a, &format!("{new} "))).collect();
            made(format!("Replace \"{old}\" with \"{new}\" on both lines."), start, (1, 0), target, format!("/{old}<CR>cgn{new}<Esc>."),
                 "Search for the words, cgn changes the match, . the next one.")
        }
        "dgn-filler" => {
            let filler = *r.choice(&["um, ", "well, ", "you know, ", "I mean, "]);
            let (plain, start) = loop {
                let plain = corpus::roomy_lines(r, 3);
                let Some((start, _)) = insert_each(r, &plain, filler.trim_end()) else { continue };
                let text = start.join("\n");
                let count = if filler.starts_with('I') { text.matches(filler).count() } else { text.to_lowercase().matches(filler).count() };
                if count == 3 {
                    break (plain, start);
                }
            };
            made(format!("Delete every \"{filler}\"."), start, (1, 0), plain, format!("/{filler}<CR>dgn.."), "dgn deletes the next match; . deletes another.")
        }
        "cgn-typo" => {
            let (word, wrong) = loop {
                let word = corpus::word(r);
                if word.len() >= 5
                    && let Some(wrong) = typo(r, &word)
                {
                    break (word, wrong);
                }
            };
            let (plain, start, at) = loop {
                let plain = lines_without(r, 3, &wrong);
                if let Some((start, at)) = insert_each(r, &plain, &wrong) {
                    break (plain, start, at);
                }
            };
            let target = plain.iter().zip(&at).map(|(l, &a)| insert(l, a, &format!("{word} "))).collect();
            made(format!("Fix every \"{wrong}\" to \"{word}\"."), start, (1, at[0] + r.below(wrong.len())), target, format!("*cgn{word}<Esc>.."),
                 "* on the typo, cgn fixes one, . the rest.")
        }

        // week 2, day 4: case and numbers
        "tilde-cap" => {
            let line = corpus::roomy(r);
            let start = format!("{}{}", line[..1].to_lowercase(), &line[1..]);
            made("Capitalise the first letter.", vec![start], (1, 0), vec![line], "~", "~ flips the case of the letter under the cursor.")
        }
        "gUiw" => {
            let (line, (a, b)) = line_with(r, |l| spans(l).into_iter().filter(|&(a, b)| b - a >= 3 && l[a..b].chars().all(|c| c.is_ascii_lowercase())).collect());
            made(format!("Uppercase \"{}\".", &line[a..b]), vec![line.clone()], (1, a + r.below(b - a)), vec![format!("{}{}{}", &line[..a], line[a..b].to_uppercase(), &line[b..])],
                 "gUiw", "gU is the uppercase operator; iw the word.")
        }
        "guu" => {
            let line = corpus::roomy(r);
            made("Make the whole line lowercase.", vec![line.to_uppercase()], (1, r.below(line.len())), vec![line.to_lowercase()], "guu", "gu lowercases; doubled, it takes the line.")
        }
        "visual-lower" => {
            let line = corpus::roomy(r);
            made("Lowercase the whole line.", vec![line.to_uppercase()], (1, r.below(line.len())), vec![line.to_lowercase()], "Vu", "V selects the line, u lowercases a selection.")
        }
        "g~iw" => {
            let (line, (a, b)) = loop {
                let line = corpus::roomy(r);
                let first = spans(&line)[0];
                if first.1 - first.0 >= 3 {
                    break (line, first);
                }
            };
            let flipped: String = line[a..b].chars().map(|c| if c.is_ascii_uppercase() { c.to_ascii_lowercase() } else { c.to_ascii_uppercase() }).collect();
            made("Flip the case of the first word.", vec![format!("{flipped}{}", &line[b..])], (1, r.below(b - a)), vec![line.clone()], "g~iw", "g~ flips case; iw is the word.")
        }
        "ctrl-a" => sum(r, "+", 1, "<C-a>".into(), "Make the sum true: Ctrl-a adds 1.".into()),
        "ctrl-x" => sum(r, "-", 1, "<C-x>".into(), "Make the sum true: Ctrl-x takes 1 away.".into()),
        "count-ctrl-a" => {
            let n = r.between(5, 40);
            sum(r, "+", n, format!("{n}<C-a>"), format!("Make the sum true: add {n}."))
        }
        "ctrl-a-dot" => {
            let label = capitalised(&corpus::term(r));
            let n: Vec<usize> = (0..3).map(|_| r.between(1, 40)).collect();
            let line = |d: usize| format!("{label}: {} {} {}", n[0] + d, n[1] + d, n[2] + d);
            made("Add one to every number.", vec![line(0)], (1, label.len() + 2), vec![line(1)], "<C-a>w.w.", "Ctrl-a on one, then w and . for each of the others.")
        }
        "star-gU" => {
            let (word, start, target, first) = loop {
                let word = corpus::word(r);
                if word.ends_with('s') {
                    continue; // its decoy is the word with an s
                }
                let plain = lines_without(r, 2, &word);
                let Some((once, _)) = insert_each(r, &plain, &word) else { continue };
                let decoy = format!("{word}s");
                let Some((with_decoy, _)) = insert_each(r, &once[..1], &decoy) else { continue };
                let start = vec![with_decoy[0].clone(), once[1].clone()];
                if start[0].len() > BOX || whole(&start.join("\n"), &word).len() != 2 {
                    continue;
                }
                let target: Vec<String> = start.iter().map(|l| replace_whole(l, &word, &word.to_uppercase())).collect();
                let first = whole(&start[0], &word)[0];
                break (word, start, target, first);
            };
            made(format!("Uppercase every \"{word}\" that stands alone."), start, (1, first + r.below(word.len())), target, "*gUiwn.",
                 "* finds the word alone, not inside a longer one; gUiw, then n and . for the other.")
        }

        // week 2, day 5: insert mode
        "o-below" | "O-above" => {
            let l = corpus::roomy_lines(r, 2);
            let new = corpus::short(r, 1).remove(0);
            let (row, key) = if kind == "o-below" { (1, 'o') } else { (2, 'O') };
            made(format!("Add the line \"{new}\" between the two."), l.clone(), (row, r.below(l[row - 1].len())), vec![l[0].clone(), new.clone(), l[1].clone()],
                 format!("{key}{new}<Esc>"), "o opens a line below, O one above, wherever the cursor is.")
        }
        "ea-append" => {
            let (line, (a, b)) = line_with(r, |l| spans(l).into_iter().filter(|&(a, b)| b - a >= 5 && l.as_bytes()[b - 1] == b's' && l.as_bytes()[b - 2] != b's').collect());
            let short = &line[a..b - 1];
            made(format!("Fix \"{short}\" to \"{}\".", &line[a..b]), vec![format!("{}{short}{}", &line[..a], &line[b..])], (1, a + r.below(short.len() - 1)), vec![line.clone()],
                 "eas<Esc>", "e goes to the end of the word, a appends after it.")
        }
        "count-insert" => {
            let title = loop {
                let t = corpus::terms(r, 2);
                let title = if r.coin() { capitalised(&t[0]) } else { format!("{} and {}", capitalised(&t[0]), t[1]) };
                if title.len() <= 20 {
                    break title;
                }
            };
            let n = title.len();
            let after = corpus::roomy(r);
            made(format!("Underline the title with {n} = signs."), vec![title.clone(), String::new(), after.clone()], (2, 0), vec![title, "=".repeat(n), after],
                 format!("{n}i=<Esc>"), format!("A count works on i: {n}i= types {n} of them."))
        }
        "R-overwrite" => {
            let date = format!("{}-{:02}-{:02}", r.between(1900, 2030), r.between(1, 12), r.between(1, 28));
            let line = corpus::roomy(r);
            made(format!("Type the date {date} over the zeros."), vec![format!("0000-00-00: {line}")], (1, 0), vec![format!("{date}: {line}")],
                 format!("R{date}<Esc>"), "R types over what is there, like the Insert key.")
        }
        "r-replace" => {
            let (line, (a, b)) = line_with(r, |l| spans(l).into_iter().filter(|&(a, b)| b - a >= 4 && l[a..b].chars().all(|c| c.is_ascii_lowercase())).collect());
            let i = a + r.below(b - a);
            let right = line.as_bytes()[i] as char;
            let wrong = loop {
                let c = (b'a' + r.below(26) as u8) as char;
                if c != right {
                    break c;
                }
            };
            let start = format!("{}{wrong}{}", &line[..i], &line[i + 1..]);
            made(format!("Fix \"{}\" to \"{}\".", &start[a..b], &line[a..b]), vec![start], (1, i), vec![line.clone()], format!("r{right}"), "r replaces the one letter under the cursor.")
        }

        // week 2, day 6: visual mode
        "visual-upper" => {
            let (line, (a, b)) = line_with(r, |l| {
                let s = spans(l);
                (0..s.len().saturating_sub(1)).filter(|&i| s[i].1 - s[i].0 >= 2 && s[i].1 + 1 == s[i + 1].0 && l.as_bytes()[s[i].1] == b' ').map(|i| (s[i].0, s[i + 1].1)).collect()
            });
            made(format!("Uppercase \"{}\".", &line[a..b]), vec![line.clone()], (1, a), vec![format!("{}{}{}", &line[..a], line[a..b].to_uppercase(), &line[b..])],
                 "veeU", "v starts a selection, e e grows it two words, U uppercases.")
        }
        "c-percent" => {
            let n = names(r, 3);
            let word = *r.choice(&["if", "while"]);
            let joiner = *r.choice(&["and not", "or", "and"]);
            let start = format!("{word} ({} {joiner} {}):", n[0], n[1]);
            made(format!("Replace the whole condition, brackets and all, with {}.", n[2]), vec![start], (1, word.len() + 1), vec![format!("{word} {}:", n[2])],
                 format!("c%{}<Esc>", n[2]), "% jumps to the matching bracket, so c% changes all of it.")
        }
        _ => return None,
    })
}

pub const KINDS: [&str; 95] = [
    "ciw-typo", "daw-double", "ciW-dotted", "dot-append", "dot-prefix", "visual-delete", "visual-indent", "visual-join", "macro-append",
    "macro-quote", "block-prefix", "block-append", "move-top", "copy-end", "range-delete", "reverse", "sort", "norm-append", "sub-prefix",
    "comments", "sort-u", "trailing", "delete-to-end", "nav-down", "nav-up", "nav-find", "ci-quote", "di-paren", "da-paren", "di-bracket",
    "dt-letter", "D-rest", "J-split", "ddp-swap", "count-dw", "count-dd", "count-x",
    // weeks 1 and 2, every task
    "ciw-ident", "ciw-url", "copy-over", "ci-paren", "cit-tag", "dap-middle", "yap-dup", "cis-sentence", "das-middle", "ip-indent",
    "ct-semi", "path-T", "nf-comma", "ct-space", "df-paren", "C-rest", "cc-line", "A-semicolon", "I-comment", "count-cw", "nf-D",
    "count-J", "count-jdd", "count-kciw", "indent-body", "dot-ciw", "dot-indent", "dot-dw", "dot-comment", "search-cw", "search-d",
    "star-ciw", "star-n-daw", "search-back", "cgn-star3", "cgn-star4", "cgn-skip", "cgn-phrase", "dgn-filler", "cgn-typo", "tilde-cap",
    "gUiw", "guu", "visual-lower", "g~iw", "ctrl-a", "ctrl-x", "count-ctrl-a", "ctrl-a-dot", "star-gU", "o-below", "O-above",
    "ea-append", "count-insert", "R-overwrite", "r-replace", "visual-upper", "c-percent",
];

/// Words of four letters or more, as (start, end); `spaced`: with a space on both sides.
fn long_words(line: &str, spaced: bool) -> Vec<(usize, usize)> {
    let bytes = line.as_bytes();
    spans(line).into_iter().filter(|&(start, end)| end - start >= 4)
        .filter(|&(start, end)| if spaced { start > 0 && bytes[start - 1] == b' ' && end < bytes.len() && bytes[end] == b' ' } else { end < bytes.len() })
        .collect()
}

/// The three word-object kinds.
fn word_task(kind: &str, r: &mut Rng) -> Made {
    let (line, (start, end)) = line_with(r, |l| {
        long_words(l, kind == "ciW-dotted").into_iter().filter(|&(start, end)| match kind {
            "daw-double" => l.as_bytes()[end] == b' ',
            "ciw-typo" => l[start + 1..end - 1].chars().collect::<HashSet<_>>().len() > 1,
            "ciW-dotted" => l.len() + (end - start) < BOX,
            _ => true,
        }).collect()
    });
    let (word, before, after) = (&line[start..end], &line[..start], &line[end..]);
    match kind {
        "ciw-typo" => {
            let shown = typo(r, word).expect("picked for two different letters inside");
            let cursor = before.len() + r.below(shown.len());
            made(format!("Fix \"{shown}\" to \"{word}\"."), vec![format!("{before}{shown}{after}")], (1, cursor), vec![line.clone()], format!("ciw{word}<Esc>"),
                 "c changes, i keeps it inner, w names the word: ciw, from anywhere inside it.")
        }
        "daw-double" => {
            let which = if r.coin() { 0 } else { word.len() + 1 };
            let cursor = before.len() + which + r.below(word.len());
            made(format!("Delete the doubled \"{word}\"."), vec![format!("{before}{word} {word}{after}")], (1, cursor), vec![line.clone()], "daw",
                 "d deletes, a takes the word with its space, w is the word: daw leaves no double space.")
        }
        _ => {
            let shown = word.chars().map(String::from).collect::<Vec<_>>().join(".");
            let cursor = before.len() + r.below(shown.len());
            made(format!("Write the dotted \"{shown}\" as \"{word}\"."), vec![format!("{before}{shown}{after}")], (1, cursor), vec![line.clone()], format!("ciW{word}<Esc>"),
                 "W is a big WORD: everything between two spaces, dots and all.")
        }
    }
}

/// Code kinds get their language, so filetype keymaps (`gcc`) work as on the written texts.
fn filetype(kind: &str) -> &'static str {
    match kind {
        "ciw-ident" | "ci-quote" | "di-paren" | "da-paren" | "di-bracket" | "ci-paren" | "ct-space" | "I-comment" | "indent-body"
        | "dot-comment" | "star-ciw" | "cgn-star3" | "c-percent" => "python",
        "cit-tag" => "html",
        _ => "",
    }
}

/// A `kind` task from `seed`, with the parent task's place in its lesson.
pub fn generate(kind: &str, seed: &str, parent: &Task) -> Task {
    let base = Task { ft: filetype(kind).into(), generated: seed.to_string(), ..parent.clone() };
    // a text wider than the box, or one that starts solved, goes back for another: the
    // same one for the same seed
    let mut tries = 0;
    let m = loop {
        let mut rng = Rng::new(&format!("{kind}:{seed}{}", "'".repeat(tries)));
        let m = if matches!(kind, "ciw-typo" | "daw-double" | "ciW-dotted") {
            word_task(kind, &mut rng)
        } else {
            make(kind, &mut rng).unwrap_or_else(|| panic!("no generator called {kind}"))
        };
        tries += 1;
        if m.start.iter().chain(&m.target).all(|l| l.len() <= BOX) && m.start != m.target {
            break m;
        }
        if tries > 50 {
            debug_assert!(false, "{kind} seed {seed}: no text fits the box");
            break m;
        }
    };
    Task { goal: m.goal, start: m.start, cursor: m.cursor, target: m.target, solution: m.solution, hint: m.hint, ..base }
}
