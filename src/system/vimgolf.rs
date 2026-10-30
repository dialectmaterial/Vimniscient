//! Challenges from vimgolf.com, played in your own Neovim. The challenge list and each
//! challenge are cached in ~/.cache/vimniscient/vimgolf/.

use crate::core::cards::home;
use crate::core::progress::Progress;
use fancy_regex::Regex;
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::LazyLock;
use std::time::{Duration, SystemTime};

const BASE: &str = "https://www.vimgolf.com";
const INDEX_MAX_AGE: Duration = Duration::from_secs(7 * 86400);
// A challenge has to fit the goal + practice split.
const MAX_LINES: usize = 40;
const MAX_WIDTH: usize = 100;
// VimGolf scores include saving and quitting (ZZ); lessons finish by themselves.
pub const SAVE_KEYS: usize = 2;

#[derive(Clone, Debug)]
pub struct Challenge {
    pub id: String,
    pub title: String,
    pub entries: u64,
    pub start: Vec<String>,
    pub target: Vec<String>,
    pub best: Option<usize>, // lowest score on the leaderboard, ZZ included
}

impl Challenge {
    pub fn url(&self) -> String {
        format!("{BASE}/challenges/{}", self.id)
    }

    pub fn fits(&self) -> bool {
        let width = self.start.iter().chain(&self.target).map(|l| l.chars().count()).max().unwrap_or(0);
        self.start.len() <= MAX_LINES && self.target.len() <= MAX_LINES && width <= MAX_WIDTH
    }
}

fn cache() -> Result<PathBuf, String> {
    let path = std::env::var_os("XDG_CACHE_HOME").map(PathBuf::from).unwrap_or_else(|| home().join(".cache")).join("vimniscient/vimgolf");
    std::fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    Ok(path)
}

fn get(url: &str, accept: &str) -> Result<String, String> {
    let mut response = ureq::get(url).header("Accept", accept).header("User-Agent", "vimniscient").call().map_err(|e| e.to_string())?;
    response.body_mut().read_to_string().map_err(|e| e.to_string())
}

fn unescape(text: &str) -> String {
    text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&#39;", "'")
}

fn lines(data: &str) -> Vec<String> {
    let data = data.replace("\r\n", "\n");
    data.strip_suffix('\n').unwrap_or(&data).split('\n').map(str::to_string).collect()
}

/// `[{id, title, entries}]`, most played first.
pub fn index() -> Result<Vec<Value>, String> {
    static ROW: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"href="/challenges/([0-9a-z]{24})">([^<]*)</a> - (\d+) entries"#).expect("a valid pattern"));
    let path = cache()?.join("index.json");
    let fresh = std::fs::metadata(&path).and_then(|m| m.modified()).ok().and_then(|t| SystemTime::now().duration_since(t).ok()).is_some_and(|age| age < INDEX_MAX_AGE);
    if fresh && let Some(list) = std::fs::read_to_string(&path).ok().and_then(|text| serde_json::from_str(&text).ok()) {
        return Ok(list);
    }
    let mut found: Vec<Value> = Vec::new();
    for page in 1..40 {
        let html = get(&format!("{BASE}/?page={page}"), "text/html")?;
        let rows: Vec<_> = ROW.captures_iter(&html).flatten().collect();
        if rows.is_empty() {
            break;
        }
        for row in rows {
            if !found.iter().any(|c| c["id"] == row[1]) {
                found.push(json!({"id": &row[1], "title": unescape(&row[2]), "entries": row[3].parse::<u64>().unwrap_or(0)}));
            }
        }
    }
    found.sort_by_key(|c| std::cmp::Reverse(c["entries"].as_u64().unwrap_or(0)));
    if !found.is_empty() {
        let _ = std::fs::write(path, json!(found).to_string());
    }
    Ok(found)
}

pub fn challenge(entry: &Value) -> Result<Challenge, String> {
    static SCORE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"href="/challenges/[0-9a-z]+/user/[^"]+">(\d+)</a>"#).expect("a valid pattern"));
    let id = entry["id"].as_str().unwrap_or_default();
    if id.len() != 24 || !id.chars().all(|c| c.is_ascii_digit() || c.is_ascii_lowercase()) {
        return Err(format!("not a VimGolf challenge id: {id:?}"));
    }
    let path = cache()?.join(format!("{id}.json"));
    let data: Value = match std::fs::read_to_string(&path).ok().and_then(|text| serde_json::from_str(&text).ok()) {
        Some(data) => data,
        None => {
            let raw: Value = serde_json::from_str(&get(&format!("{BASE}/challenges/{id}.json"), "application/json")?).map_err(|e| e.to_string())?;
            let html = get(&format!("{BASE}/challenges/{id}"), "text/html")?;
            let best = SCORE.captures(&html).ok().flatten().and_then(|c| c[1].parse::<u64>().ok());
            let data = json!({"in": raw["in"]["data"], "out": raw["out"]["data"], "best": best});
            let _ = std::fs::write(&path, data.to_string());
            data
        }
    };
    Ok(Challenge {
        id: id.to_string(),
        title: entry["title"].as_str().unwrap_or_default().to_string(),
        entries: entry["entries"].as_u64().unwrap_or(0),
        start: lines(data["in"].as_str().unwrap_or_default()),
        target: lines(data["out"].as_str().unwrap_or_default()),
        best: data["best"].as_u64().map(|b| b as usize),
    })
}

/// Today's challenge: the one given out today, else the most played one not tried yet that fits.
pub fn today(progress: &Progress) -> Result<Option<Challenge>, String> {
    let list = index()?;
    if let Some(id) = progress.vimgolf_assigned_today()
        && let Some(entry) = list.iter().find(|e| e["id"] == id.as_str())
    {
        return challenge(entry).map(Some);
    }
    let tried = progress.vimgolf_tried();
    for entry in &list {
        let (id, title) = (entry["id"].as_str().unwrap_or_default(), entry["title"].as_str().unwrap_or_default());
        if tried.contains(id) {
            continue;
        }
        let found = challenge(entry)?;
        if found.fits() {
            progress.vimgolf_assign(&found.id, &found.title, found.best);
            return Ok(Some(found));
        }
        progress.vimgolf_skip(id, title); // so it isn't fetched again tomorrow
    }
    Ok(None)
}
