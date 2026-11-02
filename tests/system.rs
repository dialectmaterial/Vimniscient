//! The helpers that run other programs and hold their files.

use std::os::unix::fs::PermissionsExt;
use std::process::{Command, Stdio};
use vimniscient::core::cards::{output_within, run};
use vimniscient::core::content::Scratch;

#[test]
fn scratch_folders_are_private_new_and_cleaned_up() {
    let (a, b) = (Scratch::new().unwrap(), Scratch::new().unwrap());
    assert_ne!(a.0, b.0);
    assert_eq!(std::fs::metadata(&a.0).unwrap().permissions().mode() & 0o777, 0o700);
    let script = a.write("nvim/keymaps.lua").unwrap();
    assert!(script.starts_with(&a.0) && script.is_file());
    let path = a.0.clone();
    drop(a);
    assert!(!path.exists());
}

#[test]
fn long_output_and_slow_programs() {
    // far more than a pipe holds: read while it runs, it doesn't stall
    assert_eq!(run("sh", &["-c", "head -c 300000 /dev/zero | tr '\\0' x"], 10).len(), 300_000);
    let started = std::time::Instant::now();
    assert!(output_within(Command::new("sleep").arg("30").stdout(Stdio::null()), 1).is_none());
    assert!(started.elapsed().as_secs() < 5);
}
