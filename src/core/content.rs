//! The YAML and Lua in `content/`, built into the binary.

use rust_embed::Embed;

#[derive(Embed)]
#[folder = "content/"]
#[include = "*.yaml"]
#[include = "*.lua"]
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

/// A built-in file written out for Neovim to read, in a folder that outlives this call.
pub fn to_temp(path: &str) -> std::io::Result<std::path::PathBuf> {
    let folder = std::env::temp_dir().join(format!("vimniscient-{}", std::process::id()));
    std::fs::create_dir_all(&folder)?;
    let file = folder.join(path.rsplit('/').next().unwrap_or(path));
    std::fs::write(&file, text(path))?;
    Ok(file)
}
