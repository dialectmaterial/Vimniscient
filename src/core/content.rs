//! The YAML and Lua in `content/`, built into the binary.

use rust_embed::Embed;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

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

/// A folder of our own for one run, gone when it's dropped. Neovim runs scripts from
/// it, so it's made new (never an existing folder someone else could have put there),
/// under a name nobody can guess, readable by you alone.
pub struct Scratch(pub PathBuf);

impl Scratch {
    pub fn new() -> std::io::Result<Scratch> {
        use std::hash::{BuildHasher, Hasher};
        use std::os::unix::fs::DirBuilderExt;
        static COUNT: AtomicUsize = AtomicUsize::new(0);
        let mut last = None;
        for _ in 0..8 {
            // RandomState is seeded from the OS's random source
            let mut hasher = std::collections::hash_map::RandomState::new().build_hasher();
            hasher.write_usize(COUNT.fetch_add(1, Ordering::Relaxed));
            hasher.write_u128(SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_nanos()));
            let path = std::env::temp_dir().join(format!("vimniscient-{}-{:016x}", std::process::id(), hasher.finish()));
            match std::fs::DirBuilder::new().mode(0o700).create(&path) {
                Ok(()) => return Ok(Scratch(path)),
                Err(error) => last = Some(error),
            }
        }
        Err(last.unwrap_or_else(|| std::io::Error::other("no scratch folder")))
    }

    /// A built-in file written out for Neovim to read.
    pub fn write(&self, path: &str) -> std::io::Result<PathBuf> {
        let file = self.0.join(path.rsplit('/').next().unwrap_or(path));
        std::fs::write(&file, text(path))?;
        Ok(file)
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
