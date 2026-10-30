//! Your settings, in ~/.config/vimniscient/config.yaml. Only one so far:
//! `minutes`, how long today's routine is meant to take.

use super::cards::home;
use serde_norway::{Mapping, Value};
use std::path::PathBuf;

const DEFAULT_MINUTES: u32 = 15;

pub fn config() -> PathBuf {
    std::env::var_os("XDG_CONFIG_HOME").map(PathBuf::from).unwrap_or_else(|| home().join(".config")).join("vimniscient/config.yaml")
}

fn read() -> Mapping {
    std::fs::read_to_string(config()).ok().and_then(|text| serde_norway::from_str(&text).ok()).unwrap_or_default()
}

pub fn minutes() -> u32 {
    read().get("minutes").and_then(Value::as_u64).filter(|&m| m > 0).map_or(DEFAULT_MINUTES, |m| m as u32)
}

pub fn set_minutes(value: u32) -> std::io::Result<()> {
    let mut data = read();
    data.insert("minutes".into(), value.into());
    let path = config();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, serde_norway::to_string(&data).unwrap_or_default())
}
