//! Counting keystrokes written in Vim key notation (`ciwfoo<Esc>`).

/// Split `ci"x<Esc>` into `c`, `i`, `"`, `x`, `<Esc>`.
pub fn split_keys(keys: &str) -> Vec<String> {
    let chars: Vec<char> = keys.chars().collect();
    let mut tokens = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '<' {
            let mut end = i + 1;
            while end < chars.len() && !matches!(chars[end], '<' | '>') && !chars[end].is_whitespace() {
                end += 1;
            }
            if end > i + 1 && end < chars.len() && chars[end] == '>' {
                tokens.push(chars[i..=end].iter().collect());
                i = end + 1;
                continue;
            }
        }
        tokens.push(chars[i].to_string());
        i += 1;
    }
    tokens
}

pub fn count_keys(keys: &str) -> usize {
    split_keys(keys).len()
}
