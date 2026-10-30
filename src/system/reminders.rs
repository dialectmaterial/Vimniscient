//! Daily practice reminders through Omarchy's own reminder system. The first comes when
//! you start using the computer, with what's left today. While something is left, another
//! comes every few hours until the evening. Once everything is done, nothing comes.
//! The follow-ups are Omarchy reminders (`omarchy-reminder-*` timers with a message file);
//! each runs `vimniscient remind` when it fires, which only notifies if work is left.

use crate::core::cards::{self, home, on_path, run};
use crate::core::lessons::{LESSONS, Lesson};
use crate::core::progress::Progress;
use crate::core::today::{self, Step};
use crate::core::drills;
use chrono::{DateTime, Local, NaiveDateTime, NaiveTime, TimeDelta};
use serde_json::Value;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};

const EVERY: i64 = 180; // minutes between reminders while something is left
const MIN_GAP: i64 = 30; // don't bother with a last reminder sooner than this before DAY_END
const LOGIN_QUIET: i64 = 60; // a login or unlock right after a reminder doesn't send another
pub const MORNING: &str = "07:00";
const GLYPH: &str = "\u{e62b}"; // the Vim logo in Nerd Fonts
const UNIT_TAG: &str = "vimniscient";

fn clock(hour: u32, minute: u32) -> NaiveTime {
    NaiveTime::from_hms_opt(hour, minute, 0).expect("a time")
}

fn day_start() -> NaiveTime {
    clock(6, 0) // no reminders before this
}

pub fn day_end() -> NaiveTime {
    clock(21, 30) // nor after this
}

pub const fn every() -> i64 {
    EVERY
}

fn folder(variable: &str, fallback: &str) -> PathBuf {
    std::env::var_os(variable).map(PathBuf::from).unwrap_or_else(|| home().join(fallback))
}

fn reminder_dir() -> PathBuf {
    PathBuf::from(std::env::var_os("XDG_RUNTIME_DIR").unwrap_or_else(|| "/tmp".into())).join("omarchy-reminders")
}

fn last_sent() -> PathBuf {
    folder("XDG_STATE_HOME", ".local/state").join("vimniscient/last-reminder")
}

fn systemd_dir() -> PathBuf {
    folder("XDG_CONFIG_HOME", ".config").join("systemd/user")
}

fn hook() -> PathBuf {
    folder("XDG_CONFIG_HOME", ".config").join("omarchy/hooks/post-boot.d/vimniscient-reminder")
}

/// This Vimniscient, run the same way from systemd or a hook.
fn this_program() -> String {
    std::env::current_exe().map(|p| p.display().to_string()).unwrap_or_else(|_| "vimniscient".into())
}

fn current_plan() -> Vec<Step> {
    let lessons: Vec<Lesson> = LESSONS.iter().filter(|l| !l.lazyvim || cards::has_lazyvim()).cloned().collect();
    let Ok(progress) = Progress::open() else { return Vec::new() };
    let work = today::todays_work(&progress, &lessons, &cards::load_decks(), &drills::load_drills(), None);
    today::plan(&progress, &lessons, &work)
}

/// (headline, body) for a notification about what's left.
fn summary(left: &[&Step]) -> (String, String) {
    let total: u32 = left.iter().map(|s| s.minutes).sum();
    let lines: Vec<String> = left.iter().map(|s| format!("{} · {} · ~{} min", s.label, s.detail, s.minutes)).collect();
    (format!("Vimniscient · about {total} min left today"), lines.join("\n"))
}

/// (timer unit, when) for the reminders still waiting, soonest first.
fn pending() -> Vec<(String, DateTime<Local>)> {
    let pattern = format!("omarchy-reminder-*{UNIT_TAG}*.timer");
    let out = run("systemctl", &["--user", "list-timers", "--all", "--output=json", &pattern], 30);
    let timers: Vec<Value> = serde_json::from_str(&out).unwrap_or_default();
    let now = Local::now();
    let mut found: Vec<(String, DateTime<Local>)> = timers.iter().filter_map(|t| {
        let at = DateTime::from_timestamp_micros(t["next"].as_i64()?)?.with_timezone(&Local);
        (at > now).then(|| (t["unit"].as_str().unwrap_or_default().to_string(), at))
    }).collect();
    found.sort_by_key(|t| t.1);
    found
}

fn cancel() {
    for (unit, _) in pending() {
        run("systemctl", &["--user", "stop", &unit], 30);
        let _ = std::fs::remove_file(reminder_dir().join(format!("{}.message", unit.trim_end_matches(".timer"))));
    }
    refresh_indicator();
}

fn refresh_indicator() {
    if on_path("omarchy-shell") {
        run("omarchy-shell", &["-q", "omarchy.indicators", "refresh"], 30);
    }
}

/// One Omarchy reminder at `at` that checks again when it fires.
fn schedule(at: NaiveDateTime, left_minutes: u32) {
    let now = Local::now();
    let minutes = (at - now.naive_local()).num_minutes().max(1);
    let unit = format!("omarchy-reminder-{minutes}m-{UNIT_TAG}-{}", now.timestamp());
    let _ = std::fs::create_dir_all(reminder_dir());
    // the label the bar and `omarchy reminder show` use
    let _ = std::fs::write(reminder_dir().join(format!("{unit}.message")), format!("Vimniscient: about {left_minutes} min of practice left"));
    let program = this_program();
    run("systemd-run", &["--user", "--quiet", "--collect", &format!("--on-active={minutes}m"), &format!("--unit={unit}"), &program, "remind", "--check"], 30);
    refresh_indicator();
}

fn notify(left: &[&Step]) {
    let (headline, body) = summary(left);
    run("omarchy-notification-send", &["-g", GLYPH, "-u", "normal", &headline, &body, "--exec", "omarchy-launch-or-focus-tui", "vimniscient"], 30);
    let path = last_sent();
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = std::fs::write(path, Local::now().format("%Y-%m-%dT%H:%M:%S").to_string());
}

fn sent_recently(minutes: i64) -> bool {
    std::fs::read_to_string(last_sent()).ok()
        .and_then(|text| NaiveDateTime::parse_from_str(text.trim(), "%Y-%m-%dT%H:%M:%S").ok())
        .is_some_and(|last| Local::now().naive_local() - last < TimeDelta::minutes(minutes))
}

fn locked() -> bool {
    Command::new("pgrep").args(["-x", "hyprlock"]).stdout(Stdio::null()).status().is_ok_and(|s| s.success())
}

/// A reminder on the lock screen gets missed: hold it until the screen is unlocked.
fn wait_for_unlock() {
    let mut waited = 0;
    while locked() && waited < 6 * 3600 {
        std::thread::sleep(std::time::Duration::from_secs(20));
        waited += 20;
    }
}

fn next_time(now: NaiveDateTime) -> Option<NaiveDateTime> {
    let at = (now + TimeDelta::minutes(EVERY)).min(now.date().and_time(day_end()));
    (at - now >= TimeDelta::minutes(MIN_GAP)).then_some(at)
}

/// `login` is a desktop start or the morning timer; otherwise a follow-up firing.
/// Returns what it did, for the command line.
pub fn remind(login: bool) -> String {
    remind_at(login, Local::now().naive_local())
}

/// The same at a given moment, so it can be tested at any time of day.
pub fn remind_at(login: bool, now: NaiveDateTime) -> String {
    wait_for_unlock();
    if now.time() < day_start() || now.time() > day_end() {
        return "outside the reminder hours".into();
    }
    let plan = current_plan();
    let left = today::left(&plan);
    if left.is_empty() {
        cancel();
        return "everything done today: no reminder".into();
    }
    if login && sent_recently(LOGIN_QUIET) && !pending().is_empty() {
        return "reminded a moment ago; the next one is already set".into();
    }
    notify(&left);
    cancel(); // one follow-up at a time
    match next_time(now) {
        Some(at) => {
            schedule(at, left.iter().map(|s| s.minutes).sum());
            format!("reminded; next check at {}", at.format("%H:%M"))
        }
        None => "reminded; that was the last one today".into(),
    }
}

/// After practising: when nothing's left, the waiting reminders go.
pub fn sync(plan: &[Step]) {
    if today::left(plan).is_empty() && !pending().is_empty() {
        cancel();
    }
}

/// The morning timer (fires on resume too, if it was asleep at 07:00) and a post-boot hook.
pub fn install() -> std::io::Result<Vec<String>> {
    let dir = systemd_dir();
    std::fs::create_dir_all(&dir)?;
    let exec = format!("{} remind --login", this_program());
    let (service, timer) = (dir.join("vimniscient-reminder.service"), dir.join("vimniscient-reminder.timer"));
    std::fs::write(&service, format!("[Unit]\nDescription=Vimniscient: remind me of today's practice\n\n[Service]\nType=oneshot\nExecStart={exec}\n"))?;
    std::fs::write(&timer, format!("[Unit]\nDescription=Vimniscient: the morning reminder\n\n[Timer]\nOnCalendar=*-*-* {MORNING}:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"))?;
    run("systemctl", &["--user", "daemon-reload"], 30);
    run("systemctl", &["--user", "enable", "--now", "vimniscient-reminder.timer"], 30);
    let script = hook();
    if let Some(parent) = script.parent() {
        std::fs::create_dir_all(parent)?;
    }
    // in the background: it waits for the first unlock, and boot shouldn't wait for it
    std::fs::write(&script, format!("#!/bin/bash\n# Vimniscient: remind me of today's practice\nsetsid {exec} >/dev/null 2>&1 &\n"))?;
    std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o755))?;
    Ok(vec![timer.display().to_string(), service.display().to_string(), script.display().to_string()])
}

pub fn uninstall() {
    run("systemctl", &["--user", "disable", "--now", "vimniscient-reminder.timer"], 30);
    for path in [systemd_dir().join("vimniscient-reminder.timer"), systemd_dir().join("vimniscient-reminder.service"), hook()] {
        let _ = std::fs::remove_file(path);
    }
    run("systemctl", &["--user", "daemon-reload"], 30);
    cancel();
}

pub fn status() -> String {
    let plan = current_plan();
    let left = today::left(&plan);
    let mut lines = Vec::new();
    if left.is_empty() {
        lines.push("Everything done today.".to_string());
    } else {
        let (headline, body) = summary(&left);
        lines.push(headline);
        lines.push(body);
    }
    let waiting = pending();
    lines.push(format!("Next reminder: {}", waiting.first().map_or("none set".to_string(), |t| t.1.format("%H:%M").to_string())));
    let enabled = run("systemctl", &["--user", "is-enabled", "vimniscient-reminder.timer"], 30);
    lines.push(format!("Morning reminder ({MORNING}, or when you start): {}", if enabled.trim() == "enabled" { "on" } else { "off" }));
    lines.join("\n")
}
