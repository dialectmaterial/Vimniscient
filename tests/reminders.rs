//! Reminders at fixed times of day, with the desktop's commands replaced by stand-ins
//! that only write down how they were called.

use chrono::{Local, NaiveTime};
use std::os::unix::fs::PermissionsExt;
use vimniscient::system::reminders;

#[test]
fn reminds_when_practice_is_left() {
    let dir = std::env::temp_dir().join(format!("vimniscient-remind-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    let bin = dir.join("bin");
    std::fs::create_dir_all(&bin).unwrap();
    let log = dir.join("calls.log");
    for name in ["omarchy-notification-send", "systemd-run", "systemctl", "pgrep"] {
        let script = bin.join(name);
        let exit = if name == "pgrep" { 1 } else { 0 };
        std::fs::write(&script, format!("#!/bin/sh\necho \"{name} $*\" >> {}\nexit {exit}\n", log.display())).unwrap();
        std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o755)).unwrap();
    }
    let path = format!("{}:/usr/bin:/bin", bin.display());
    // SAFETY: the only test in this binary, setting these before any thread reads them.
    unsafe {
        std::env::set_var("PATH", path);
        std::env::set_var("VIMNISCIENT_DATA", dir.join("data"));
        std::env::set_var("XDG_CONFIG_HOME", dir.join("config"));
        std::env::set_var("XDG_STATE_HOME", dir.join("state"));
        std::env::set_var("XDG_RUNTIME_DIR", dir.join("run"));
        std::env::set_var("XDG_CACHE_HOME", dir.join("cache"));
    }
    let at = |h, m| Local::now().date_naive().and_time(NaiveTime::from_hms_opt(h, m, 0).unwrap());

    assert_eq!(reminders::remind_at(false, at(23, 0)), "outside the reminder hours");
    assert_eq!(reminders::remind_at(false, at(5, 0)), "outside the reminder hours");
    assert!(!std::fs::read_to_string(&log).unwrap_or_default().contains("notification"), "nothing sent outside the hours");

    assert_eq!(reminders::remind_at(false, at(9, 0)), "reminded; next check at 12:00");
    let calls = std::fs::read_to_string(&log).unwrap();
    assert!(calls.contains("omarchy-notification-send"), "{calls}");
    assert!(calls.contains("Vimniscient · about"), "{calls}");
    assert!(calls.contains("Lesson · W1 D1"), "{calls}");
    let timer = calls.lines().find(|l| l.starts_with("systemd-run")).expect("a follow-up");
    assert!(timer.contains("--on-active=") && timer.contains("remind --check"), "{timer}");

    assert_eq!(reminders::remind_at(false, at(21, 15)), "reminded; that was the last one today");
    let _ = std::fs::remove_dir_all(&dir);
}
