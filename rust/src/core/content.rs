//! The YAML and Lua the Python app also reads, built into the binary.

use rust_embed::Embed;

#[derive(Embed)]
#[folder = "../src/vimniscient/"]
#[include = "*.yaml"]
#[include = "*.lua"]
#[exclude = "__pycache__/*"]
pub struct Content;

pub fn text(path: &str) -> String {
    let file = Content::get(path).unwrap_or_else(|| panic!("no built-in file {path}"));
    String::from_utf8_lossy(&file.data).into_owned()
}

/// The built-in files under `folder`, sorted by name.
pub fn names(folder: &str) -> Vec<String> {
    let prefix = format!("{folder}/");
    let mut found: Vec<String> = Content::iter().filter(|name| name.starts_with(&prefix)).map(|name| name.into_owned()).collect();
    found.sort();
    found
}

/// A YAML scalar as Python's `str()` would give it: `3f` and `0` are both keys here.
pub fn scalar(value: &serde_norway::Value) -> String {
    use serde_norway::Value;
    match value {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => if *b { "True".into() } else { "False".into() },
        _ => String::new(),
    }
}
