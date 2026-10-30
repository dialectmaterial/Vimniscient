//! The live desktop for Omarchy drills: the drill window and the event stream.

use crate::core::drills::socket;
use serde_json::Value;
use std::io::{BufRead, BufReader};
use std::os::unix::net::UnixStream;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::Sender;
use std::time::Duration;

const DRILL_CLASS: &str = "vimniscient-drill";
const DRILL_TITLE: &str = "Vimniscient drill";

fn hyprctl(what: &str) -> Value {
    let out = crate::core::cards::run("hyprctl", &[what, "-j"], 5);
    serde_json::from_str(&out).unwrap_or(Value::Null)
}

pub fn available() -> bool {
    socket().is_some()
}

pub fn home() -> String {
    hyprctl("activeworkspace")["id"].to_string()
}

fn drill_address() -> Option<String> {
    hyprctl("clients").as_array()?.iter().find(|c| c["class"] == DRILL_CLASS).map(|c| c["address"].as_str().unwrap_or_default().trim_start_matches("0x").to_string())
}

/// Open the drill window if it isn't there; returns its address.
pub fn ensure_drill_window(window: &mut Option<Child>) -> Option<String> {
    if let Some(address) = drill_address() {
        return Some(address);
    }
    let text = "This is the drill window.\\nThe drills happen to it, so your own windows are left alone.";
    // it closes itself once the trainer is gone, even if that crashed
    let script = format!("printf \"\\n  {text}\\n\"; while kill -0 {} 2>/dev/null; do sleep 2; done", std::process::id());
    *window = Command::new("xdg-terminal-exec").arg(format!("--app-id={DRILL_CLASS}")).arg(format!("--title={DRILL_TITLE}"))
        .args(["-e", "sh", "-c", &script]).stdout(Stdio::null()).stderr(Stdio::null()).spawn().ok();
    for _ in 0..50 {
        std::thread::sleep(Duration::from_millis(100));
        if let Some(address) = drill_address() {
            return Some(address);
        }
    }
    None
}

pub fn close_drill_window(window: &mut Option<Child>) {
    if let Some(address) = drill_address() {
        crate::core::cards::run("hyprctl", &["dispatch", &format!("hl.dsp.window.close({{ window = \"address:0x{address}\" }})")], 5);
    }
    if let Some(child) = window {
        let _ = child.kill();
        let _ = child.wait();
    }
    *window = None;
}

/// Send `event>>data` lines to `out` until the socket or the receiver goes away.
pub fn listen(out: Sender<super::super::ui::Message>) {
    let Some(path) = socket() else { return };
    std::thread::spawn(move || {
        let Ok(stream) = UnixStream::connect(path) else { return };
        for line in BufReader::new(stream).lines().map_while(Result::ok) {
            if out.send(super::super::ui::Message::Hyprland(line)).is_err() {
                return;
            }
        }
    });
}
