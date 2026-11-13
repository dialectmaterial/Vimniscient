mod common;

use std::os::unix::fs::PermissionsExt;
use vimniscient::core::{cards, lessons::LESSONS, progress::{Progress, today}, srs::Item};

#[test]
fn reviews_exclude_unused_tools_without_erasing_history() {
    let dir = std::env::temp_dir().join(format!("vimniscient-review-decks-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    // SAFETY: this binary has one test; environment setup precedes all readers.
    unsafe {
        std::env::set_var("HOME", &dir);
        std::env::set_var("VIMNISCIENT_DATA", dir.join("data"));
        std::env::set_var("XDG_CONFIG_HOME", dir.join("config"));
        std::env::set_var("XDG_STATE_HOME", dir.join("state"));
    }
    common::fake_machine(&dir);
    let marker = dir.join("tmux-loaded");
    for (name, script) in [
        ("omarchy", "#!/bin/sh\nprintf 'SUPER + RETURN → Terminal\\n'\n".to_string()),
        ("omarchy-menu-tmux-keybindings", format!("#!/bin/sh\ntouch '{}'\nprintf 'PREFIX + c → New window\\n'\n", marker.display())),
    ] {
        let path = dir.join("fake-bin").join(name);
        std::fs::write(&path, script).unwrap();
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755)).unwrap();
    }
    let decks = cards::load_decks();
    assert!(!decks.contains_key("lazyvim"));
    assert!(!decks.contains_key("tmux"));
    assert!(!cards::load_static_decks().contains_key("lazyvim"));
    assert!(!marker.exists(), "must not execute the tmux binding loader");
    assert_eq!(decks["omarchy"].cards[0].prompt, "Terminal");

    let progress = Progress::open().unwrap();
    let active = &decks["omarchy"].cards[0];
    for id in [active.id.as_str(), "lazyvim:old", "tmux:New window"] {
        let mut item = Item::new(id, "card");
        item.due = Some(today());
        progress.save(&item);
    }
    let due = progress.due_cards(&decks, &LESSONS, None);
    assert!(due.iter().any(|card| card.id == active.id));
    assert!(due.iter().all(|card| card.deck != "lazyvim" && card.deck != "tmux"));
    assert!(progress.item("lazyvim:old").is_some());
    assert!(progress.item("tmux:New window").is_some());
    std::fs::remove_dir_all(dir).unwrap();
}
