//! Live Omarchy drills, checked against Hyprland's events. The matching (`DrillRun`)
//! is plain and testable; the desktop itself is in `system::hyprland`.

use super::{content, srs};
use serde_norway::Value;
use std::path::PathBuf;
use std::time::Instant;

#[derive(Clone, Debug)]
pub struct Step {
    pub event: String,
    pub args: Vec<String>,
    pub done: String,
    pub active: Option<String>,
}

#[derive(Clone, Debug)]
pub struct Drill {
    pub id: String,
    pub title: String,
    pub prompt: String,
    pub bindings: Vec<String>,
    pub steps: Vec<Step>,
}

impl Drill {
    pub fn item_id(&self) -> String {
        format!("drill:{}", self.id)
    }
}

pub fn load_drills() -> Vec<Drill> {
    let data: Value = serde_norway::from_str(&content::text("drills/omarchy.yaml")).expect("omarchy.yaml");
    let strings = |value: Option<&Value>| value.and_then(Value::as_sequence).map(|items| items.iter().map(content::scalar).collect::<Vec<_>>()).unwrap_or_default();
    data["drills"].as_sequence().expect("drills").iter().map(|d| Drill {
        id: content::scalar(&d["id"]),
        title: content::scalar(&d["title"]),
        prompt: content::scalar(&d["prompt"]),
        bindings: strings(d.get("bindings")),
        steps: d["steps"].as_sequence().expect("steps").iter().map(|s| Step {
            event: content::scalar(&s["event"]),
            args: strings(s.get("args")),
            done: content::scalar(&s["done"]),
            active: s.get("active").map(content::scalar),
        }).collect(),
    }).collect()
}

/// Walks one drill's steps as events come in.
pub struct DrillRun {
    pub drill: Drill,
    pub drill_addr: String, // without 0x, as the events write it
    pub home: String, // workspace id
    pub step: usize,
    pub active: String, // address of the focused window
    pub new: Option<String>,
    pub started: Instant,
}

impl DrillRun {
    pub fn new(drill: Drill, drill_addr: String, home: String) -> DrillRun {
        DrillRun { drill, drill_addr, home, step: 0, active: String::new(), new: None, started: Instant::now() }
    }

    pub fn away(&self) -> &str {
        if self.home == "9" { "8" } else { "9" }
    }

    pub fn text(&self, template: &str) -> String {
        template.replace("{home}", &self.home).replace("{away}", self.away())
    }

    pub fn finished(&self) -> bool {
        self.step >= self.drill.steps.len()
    }

    fn arg_ok(&mut self, pattern: &str, value: &str) -> bool {
        match pattern {
            "*" => true,
            "$drill" => value == self.drill_addr,
            "$home" => value == self.home,
            "$away" => value == self.away(),
            "!drill" => !value.is_empty() && value != self.drill_addr,
            "$new" => match &self.new {
                None if !value.is_empty() && value != self.drill_addr => {
                    self.new = Some(value.to_string());
                    true
                }
                None => false,
                Some(new) => value == new,
            },
            _ => value == pattern,
        }
    }

    /// Take one `event>>data` line; true when it completed a step.
    pub fn feed(&mut self, line: &str) -> bool {
        let (name, data) = line.split_once(">>").unwrap_or((line, ""));
        if name == "activewindowv2" {
            self.active = data.trim_start_matches("0x").to_string();
        }
        if self.finished() {
            return false;
        }
        let step = self.drill.steps[self.step].clone();
        if name != step.event {
            return false;
        }
        let args: Vec<&str> = if step.args.is_empty() { Vec::new() } else { data.splitn(step.args.len(), ',').collect() };
        if args.len() != step.args.len() || (step.active.as_deref() == Some("$drill") && self.active != self.drill_addr) {
            return false;
        }
        let before = self.new.clone();
        if !step.args.iter().zip(&args).all(|(pattern, value)| self.arg_ok(pattern, value)) {
            self.new = before;
            return false;
        }
        self.step += 1;
        true
    }
}

pub fn grade(seconds: f64, hinted: bool, skipped: bool) -> u8 {
    if skipped {
        srs::AGAIN
    } else if hinted {
        srs::HARD
    } else if seconds <= 10.0 {
        srs::EASY
    } else if seconds <= 30.0 {
        srs::GOOD
    } else {
        srs::HARD
    }
}

/// Hyprland's event socket, when there's a session to listen to.
pub fn socket() -> Option<PathBuf> {
    let signature = std::env::var_os("HYPRLAND_INSTANCE_SIGNATURE")?;
    let path = PathBuf::from(std::env::var_os("XDG_RUNTIME_DIR").unwrap_or_default()).join("hypr").join(signature).join(".socket2.sock");
    path.exists().then_some(path)
}
