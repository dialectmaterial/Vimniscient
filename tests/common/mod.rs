//! The same machine for every test, wherever it runs: LazyVim installed, and the
//! programs some decks need on the PATH (stand-ins that do nothing). The golden files
//! were recorded with all of them present.

use std::os::unix::fs::PermissionsExt;
use std::path::Path;

/// Call before any thread reads the environment.
pub fn fake_machine(dir: &Path) {
    let data = dir.join("xdg-data");
    std::fs::create_dir_all(data.join("nvim/lazy/LazyVim")).unwrap();
    let bin = dir.join("fake-bin");
    std::fs::create_dir_all(&bin).unwrap();
    for program in ["foot", "zathura"] {
        let path = bin.join(program);
        std::fs::write(&path, "#!/bin/sh\nexit 0\n").unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).unwrap();
    }
    let path = format!("{}:{}", bin.display(), std::env::var("PATH").unwrap_or_default());
    // SAFETY: the callers are single-test binaries that do this before starting threads.
    unsafe {
        std::env::set_var("XDG_DATA_HOME", data);
        std::env::set_var("PATH", path);
    }
}
