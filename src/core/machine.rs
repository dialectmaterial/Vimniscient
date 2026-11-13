//! What's on this machine: its folders, the programs on PATH, Neovim plugins, and
//! running a command with a time limit.

use std::io::Read;
use std::path::PathBuf;
use std::process::{Command, Output, Stdio};
use std::time::{Duration, Instant};

pub fn home() -> PathBuf {
    std::env::var_os("HOME").map(PathBuf::from).unwrap_or_default()
}

/// An XDG base folder: `$variable`, or `fallback` under your home when it's unset.
fn xdg(variable: &str, fallback: &str) -> PathBuf {
    std::env::var_os(variable).map(PathBuf::from).unwrap_or_else(|| home().join(fallback))
}

pub fn config_home() -> PathBuf {
    xdg("XDG_CONFIG_HOME", ".config")
}

pub fn data_home() -> PathBuf {
    xdg("XDG_DATA_HOME", ".local/share")
}

pub fn state_home() -> PathBuf {
    xdg("XDG_STATE_HOME", ".local/state")
}

pub fn cache_home() -> PathBuf {
    xdg("XDG_CACHE_HOME", ".cache")
}

pub fn nvim_data() -> PathBuf {
    data_home().join("nvim")
}

/// A Neovim plugin installed through lazy.nvim.
pub fn has_plugin(name: &str) -> bool {
    nvim_data().join("lazy").join(name).is_dir()
}

/// LazyVim's lessons need it.
pub fn has_lazyvim() -> bool {
    has_plugin("LazyVim")
}

pub fn on_path(program: &str) -> bool {
    std::env::var_os("PATH").is_some_and(|path| std::env::split_paths(&path).any(|dir| dir.join(program).is_file()))
}

/// Run `command` to the end, at most `seconds`; None when it won't start or is too slow.
/// Its output is read while it runs, so a long one can't fill the pipe and stall.
pub fn output_within(command: &mut Command, seconds: u64) -> Option<Output> {
    fn drain(pipe: Option<impl Read + Send + 'static>) -> std::thread::JoinHandle<Vec<u8>> {
        std::thread::spawn(move || {
            let mut bytes = Vec::new();
            if let Some(mut pipe) = pipe {
                let _ = pipe.read_to_end(&mut bytes);
            }
            bytes
        })
    }
    let mut child = command.stdin(Stdio::null()).spawn().ok()?;
    let (stdout, stderr) = (drain(child.stdout.take()), drain(child.stderr.take()));
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if started.elapsed() < Duration::from_secs(seconds) => std::thread::sleep(Duration::from_millis(20)),
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
        }
    };
    let (stdout, stderr) = (stdout.join().unwrap_or_default(), stderr.join().unwrap_or_default());
    status.map(|status| Output { status, stdout, stderr })
}

/// What a command prints, or nothing when it fails or takes more than `seconds`.
pub fn run(program: &str, args: &[&str], seconds: u64) -> String {
    output_within(Command::new(program).args(args).stdout(Stdio::piped()).stderr(Stdio::null()), seconds)
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default()
}
