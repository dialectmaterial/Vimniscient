//! `vimniscient doctor`: does this machine work with the trainer? Required checks stop
//! it working; the rest say what you'd be missing.

use crate::core::cards::{has_lazyvim, has_plugin, on_path};
use crate::core::progress::data_dir;
use fancy_regex::Regex;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const MIN_NVIM: (u32, u32) = (0, 10);
const MIN_SIZE: (u16, u16) = (80, 24);

pub struct Check {
    pub name: &'static str,
    pub passed: bool,
    pub detail: String,
    pub required: bool,
}

impl Check {
    pub fn mark(&self) -> &'static str {
        if self.passed { "✓" } else if self.required { "✗" } else { "·" }
    }
}

fn check(name: &'static str, passed: bool, detail: impl Into<String>, required: bool) -> Check {
    Check { name, passed, detail: detail.into(), required }
}

fn nvim() -> Vec<Check> {
    let wanted = format!("{}.{}", MIN_NVIM.0, MIN_NVIM.1);
    if !on_path("nvim") {
        return vec![check("Neovim", false, format!("not found; install {wanted} or newer"), true)];
    }
    let out = Command::new("nvim").arg("--version").output().map(|o| String::from_utf8_lossy(&o.stdout).into_owned()).unwrap_or_default();
    let found = Regex::new(r"v(\d+)\.(\d+)").ok().and_then(|re| re.captures(&out).ok().flatten());
    let version = found.map_or((0, 0), |c| (c[1].parse().unwrap_or(0), c[2].parse().unwrap_or(0)));
    let good = version >= MIN_NVIM;
    let detail = format!("{}.{}{}", version.0, version.1, if good { String::new() } else { format!("; {wanted} or newer needed") });
    vec![check("Neovim", good, detail, true), config()]
}

fn config() -> Check {
    let child = Command::new("nvim").args(["--headless", "-i", "NONE", "+qa"]).stdout(Stdio::null()).stderr(Stdio::piped()).spawn();
    let Ok(mut child) = child else { return check("Your config", false, "Neovim wouldn't start", true) };
    let started = Instant::now();
    while child.try_wait().ok().flatten().is_none() {
        if started.elapsed() > Duration::from_secs(30) {
            let _ = child.kill();
            return check("Your config", false, "Neovim didn't start within 30 seconds", true);
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    let Ok(run) = child.wait_with_output() else { return check("Your config", false, "Neovim wouldn't start", true) };
    let errors = String::from_utf8_lossy(&run.stderr).into_owned();
    let problem = errors.lines().find(|line| line.to_lowercase().contains("error")).unwrap_or("");
    let shown: String = problem.chars().take(90).collect();
    let clean = run.status.success() && problem.is_empty();
    check("Your config", clean, if shown.is_empty() { "starts cleanly".to_string() } else { shown }, true)
}

fn terminal() -> Check {
    let (columns, lines) = crossterm::terminal::size().unwrap_or((80, 24));
    let good = columns >= MIN_SIZE.0 && lines >= MIN_SIZE.1;
    let extra = if good { String::new() } else { format!("; {}×{} or larger is needed", MIN_SIZE.0, MIN_SIZE.1) };
    check("Terminal size", good, format!("{columns}×{lines}{extra}"), false)
}

fn data() -> Check {
    let path = data_dir().join("progress.db");
    let opened = std::fs::create_dir_all(data_dir()).map_err(|e| e.to_string())
        .and_then(|()| rusqlite::Connection::open(&path).and_then(|db| db.execute_batch("SELECT 1")).map_err(|e| e.to_string()));
    match opened {
        Ok(()) => check("Progress data", true, path.display().to_string(), true),
        Err(error) => check("Progress data", false, format!("{}: {error}", path.display()), true),
    }
}

pub fn checks() -> Vec<Check> {
    let mut found = nvim();
    found.push(data());
    found.push(terminal());
    let lazyvim = has_lazyvim();
    found.push(check("LazyVim", lazyvim, format!("week 5 lessons and the LazyVim cards{}", if lazyvim { "" } else { " stay hidden" }), false));
    found.push(check("hardtime.nvim", has_plugin("hardtime.nvim"), "habit cards and drills", false));
    found.push(check("Hyprland", std::env::var_os("HYPRLAND_INSTANCE_SIGNATURE").is_some_and(|s| !s.is_empty()), "Omarchy drills", false));
    found
}
