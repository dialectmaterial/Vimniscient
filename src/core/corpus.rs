//! Practice text: sentences from two public-domain linguistics books and names built
//! from linguistics terms (content/corpus/sources.md). Generated tasks take their
//! text from here, so Recall and reviews practise a skill, not a remembered sentence.

use super::content;
use super::generate::Rng;
use std::collections::HashSet;
use std::sync::LazyLock;

/// Every line: plain words, commas and a closing full stop, 14 to 70 characters.
pub static PROSE: LazyLock<Vec<String>> = LazyLock::new(|| content::text("corpus/prose.txt").lines().map(str::to_string).collect());

/// Lines with room for a few more words: 26 to 56 characters.
static ROOMY: LazyLock<Vec<&'static str>> = LazyLock::new(|| PROSE.iter().filter(|l| (26..=56).contains(&l.len())).map(String::as_str).collect());

/// Sentences short enough for three on a line.
static SHORT: LazyLock<Vec<&'static str>> = LazyLock::new(|| PROSE.iter().filter(|l| l.len() <= 22).map(String::as_str).collect());

const COMMON: [&str; 40] = [
    "this", "that", "with", "from", "have", "were", "which", "their", "there", "they", "been", "into", "than", "more", "only", "other",
    "such", "some", "what", "when", "will", "would", "these", "those", "them", "then", "very", "much", "also", "each", "even", "most",
    "upon", "where", "while", "shall", "could", "should", "about", "being",
];

/// Lowercase words of 4 to 9 letters from the prose, the commonest function words left out.
pub static WORDS: LazyLock<Vec<String>> = LazyLock::new(|| {
    let mut seen = HashSet::new();
    PROSE.iter().flat_map(|l| l.split([' ', ',', '.']))
        .filter(|w| (4..=9).contains(&w.len()) && w.chars().all(|c| c.is_ascii_lowercase()) && !COMMON.contains(w))
        .filter(|w| seen.insert(w.to_string()))
        .map(str::to_string)
        .collect()
});

pub static TERMS: LazyLock<Vec<String>> = LazyLock::new(|| content::text("corpus/terms.txt").lines().map(str::to_string).filter(|l| !l.is_empty()).collect());

/// `n` different items of `pool`.
pub fn distinct<T: Clone + PartialEq>(r: &mut Rng, pool: &[T], n: usize) -> Vec<T> {
    let mut picked: Vec<T> = Vec::with_capacity(n);
    while picked.len() < n {
        let item = r.choice(pool);
        if !picked.contains(item) {
            picked.push(item.clone());
        }
    }
    picked
}

/// A line that still fits the box with a few words added.
pub fn roomy(r: &mut Rng) -> String {
    r.choice(&ROOMY).to_string()
}

pub fn roomy_lines(r: &mut Rng, n: usize) -> Vec<String> {
    distinct(r, &ROOMY, n).into_iter().map(str::to_string).collect()
}

pub fn short(r: &mut Rng, n: usize) -> Vec<String> {
    distinct(r, &SHORT, n).into_iter().map(str::to_string).collect()
}

pub fn word(r: &mut Rng) -> String {
    r.choice(&WORDS).clone()
}

pub fn words(r: &mut Rng, n: usize) -> Vec<String> {
    distinct(r, &WORDS, n)
}

pub fn term(r: &mut Rng) -> String {
    r.choice(&TERMS).clone()
}

pub fn terms(r: &mut Rng, n: usize) -> Vec<String> {
    distinct(r, &TERMS, n)
}

/// `n` different snake_case names: `split_morpheme`, `stem`, `vowel_shift`.
pub fn names(r: &mut Rng, n: usize) -> Vec<String> {
    let mut found: Vec<String> = Vec::with_capacity(n);
    while found.len() < n {
        let name = if r.below(3) == 0 { term(r) } else { format!("{}_{}", term(r), term(r)) };
        let parts: Vec<&str> = name.split('_').collect();
        if parts.len() == 2 && parts[0] == parts[1] || name.len() > 18 || found.contains(&name) {
            continue;
        }
        found.push(name);
    }
    found
}

/// The words of a line as (start, end) byte ranges: runs of letters.
pub fn spans(line: &str) -> Vec<(usize, usize)> {
    let bytes = line.as_bytes();
    let mut found = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i].is_ascii_alphabetic() {
            let start = i;
            while i < bytes.len() && bytes[i].is_ascii_alphabetic() {
                i += 1;
            }
            found.push((start, i));
        } else {
            i += 1;
        }
    }
    found
}

/// Where a new word can go: the start of every word with a space before it.
pub fn gaps(line: &str) -> Vec<usize> {
    spans(line).into_iter().map(|(start, _)| start).filter(|&s| s > 0 && line.as_bytes()[s - 1] == b' ').collect()
}

/// Case-insensitive positions of `word` as a whole word, as `*` finds it.
pub fn whole(text: &str, word: &str) -> Vec<usize> {
    let (hay, needle) = (text.to_lowercase(), word.to_lowercase());
    let bytes = hay.as_bytes();
    let is_word = |b: u8| b.is_ascii_alphanumeric() || b == b'_';
    hay.match_indices(&needle).map(|(i, _)| i)
        .filter(|&i| (i == 0 || !is_word(bytes[i - 1])) && (i + needle.len() >= bytes.len() || !is_word(bytes[i + needle.len()])))
        .collect()
}

/// Where `/pattern` matches, with smartcase: case matters only once it has a capital.
fn matches(text: &str, pattern: &str) -> Vec<usize> {
    let (hay, needle) = if pattern.chars().any(|c| c.is_ascii_uppercase()) { (text.to_string(), pattern.to_string()) } else { (text.to_lowercase(), pattern.to_string()) };
    (0..hay.len()).filter(|&i| hay[i..].starts_with(&needle)).collect()
}

/// The shortest start of `word` that a search from `from` finds first at `at`, forward
/// (`/`) or backward (`?`), in `text` (the lines joined with newlines).
pub fn shortest_search(text: &str, from: usize, at: usize, word: &str, forward: bool) -> Option<String> {
    (1..=word.len()).map(|n| &word[..n]).find(|pattern| {
        let found = matches(text, pattern);
        let first = if forward { found.iter().find(|&&i| i > from).or(found.first()) } else { found.iter().rev().find(|&&i| i < from).or(found.last()) };
        first == Some(&at)
    }).map(str::to_string)
}

pub fn ordinal(n: usize) -> &'static str {
    ["zeroth", "first", "second", "third", "fourth", "fifth", "sixth"][n.min(6)]
}

pub fn capitalised(s: &str) -> String {
    let mut chars = s.chars();
    chars.next().map(|c| c.to_ascii_uppercase().to_string() + chars.as_str()).unwrap_or_default()
}
