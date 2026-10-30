//! Every screen, driven without a terminal: it opens, shows what it should, and the
//! keys that move between screens work. A port of tests/check_app.py.

use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::{Terminal, backend::TestBackend};
use vimniscient::core::cards;
use vimniscient::core::lessons::{LESSONS, two_rounds};
use vimniscient::core::results::TaskResult;
use vimniscient::ui::app::{App, Job, Screen};

fn press(app: &mut App, keys: &str) {
    for c in keys.chars() {
        app.press(KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE));
    }
}

fn special(app: &mut App, key: KeyCode) {
    app.press(KeyEvent::new(key, KeyModifiers::NONE));
}

fn screen(app: &App) -> String {
    let mut terminal = Terminal::new(TestBackend::new(120, 40)).unwrap();
    terminal.draw(|frame| app.draw(frame)).unwrap();
    let buffer = terminal.backend().buffer().clone();
    (0..40).map(|y| (0..120).map(|x| buffer[(x, y)].symbol().to_string()).collect::<String>() + "\n").collect()
}

fn on_main(app: &App) -> bool {
    matches!(app.screens.last(), Some(Screen::Main(_))) && app.screens.len() == 1
}

#[test]
fn every_screen() {
    let dir = std::env::temp_dir().join(format!("vimniscient-ui-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    // SAFETY: the only test in this binary, setting these before any thread reads them.
    unsafe {
        std::env::set_var("VIMNISCIENT_DATA", dir.join("data"));
        std::env::set_var("XDG_CONFIG_HOME", dir.join("config"));
        std::env::set_var("XDG_STATE_HOME", dir.join("state"));
    }
    let lessons: &'static [_] = Box::leak(LESSONS.clone().into_boxed_slice());
    let mut app = App::with(lessons, cards::load_static_decks());
    assert!(on_main(&app));
    let ids: Vec<String> = app.plan().iter().map(|s| s.id.clone()).collect();
    assert_eq!(ids[..4], ["cards", "drills", "review", "lesson"]);
    assert!(ids.contains(&"transfer".to_string()));
    let shown = screen(&app);
    for text in ["1 Today", "2 Lessons", "Progress", "Word text objects", "Week 1", "t today", "New here?"] {
        assert!(shown.contains(text), "{text} not on the main screen:\n{shown}");
    }

    // the highlight runs the whole width of its pane
    let mut terminal = Terminal::new(TestBackend::new(120, 40)).unwrap();
    terminal.draw(|frame| app.draw(frame)).unwrap();
    let buffer = terminal.backend().buffer().clone();
    assert_eq!(buffer[(2, 1)].bg, buffer[(40, 1)].bg, "the Today highlight stops short");

    // holding j keeps moving; the detail follows at once
    press(&mut app, "2");
    let before = screen(&app);
    press(&mut app, "jj");
    assert_ne!(screen(&app), before);
    press(&mut app, "1");

    press(&mut app, "s");
    assert!(matches!(app.screens.last(), Some(Screen::Stats(_))));
    assert!(screen(&app).contains("Card accuracy"));
    special(&mut app, KeyCode::Esc);
    assert!(on_main(&app));

    press(&mut app, "c");
    assert!(matches!(app.screens.last(), Some(Screen::Cards(_))));
    let first = app.progress.new_cards(&app.decks, app.lessons)[0].clone();
    assert!(screen(&app).contains(&first.shown()), "a first card is introduced, answer shown");
    press(&mut app, "x");
    special(&mut app, KeyCode::Enter);
    assert!(screen(&app).contains("type it as shown"), "a wrong copy asks again");
    press(&mut app, &first.answers[0]);
    special(&mut app, KeyCode::Enter);
    let Some(Screen::Cards(cards)) = app.screens.last() else { panic!() };
    assert!(cards.session.as_ref().unwrap().pending.is_some(), "the right copy is taken");
    special(&mut app, KeyCode::Esc);
    assert!(on_main(&app));

    let lesson = &app.lessons[0];
    let tasks = two_rounds(lesson, "2026-10-30");
    let results: Vec<TaskResult> = tasks.iter().enumerate().map(|(i, t)| {
        let mut r = TaskResult::new(t, if i == 8 { "skipped" } else { "solved" }, &t.solution, t.reference(), 0);
        r.seconds = Some(4.0);
        r.first = Some(1.0);
        r
    }).collect();
    app.show_results(lesson.clone(), results.clone(), String::new(), String::new(), Some(Job::Lesson(lesson.clone())));
    let shown = screen(&app);
    assert!(shown.contains("5 of 6 recalled"), "{shown}");
    assert!(shown.contains("4.0s a task"), "{shown}");
    assert!(shown.contains("Why these keys"), "{shown}");
    assert!(!shown.contains("Your keys"), "clean keys get no advice");
    special(&mut app, KeyCode::Enter);
    assert!(on_main(&app));

    app.show_results(lesson.clone(), vec![TaskResult::new(&tasks[6], "solved", "jjjjjdd", 7, 0)], String::new(), String::new(), None);
    assert!(screen(&app).contains("j 5 times"));
    press(&mut app, "q");

    app.show_results(lesson.clone(), results, "Another way\nGoal  [ci(x<Esc>".into(), String::new(), None);
    assert!(screen(&app).contains("[ci(x"), "a note shows, brackets and all");
    special(&mut app, KeyCode::Esc);

    press(&mut app, "z");
    assert!(matches!(app.screens.last(), Some(Screen::Quick(_))));
    assert!(screen(&app).contains("Navigation"));
    special(&mut app, KeyCode::Enter);
    assert!(matches!(app.pending.take(), Some(Job::Quick(_))), "navigation starts");
    assert!(on_main(&app));

    press(&mut app, "e");
    assert!(matches!(app.screens.last(), Some(Screen::Intro(_))));
    assert!(screen(&app).contains("Endless"));
    special(&mut app, KeyCode::Esc);
    assert!(on_main(&app));

    press(&mut app, "p");
    assert!(screen(&app).contains("Placement test"));
    special(&mut app, KeyCode::Enter);
    assert!(matches!(app.pending.take(), Some(Job::Placement)));
    assert!(on_main(&app));

    press(&mut app, "2");
    special(&mut app, KeyCode::Enter);
    assert!(matches!(app.pending.take(), Some(Job::Lesson(_))), "Enter on a lesson runs it");

    press(&mut app, "q");
    assert!(app.quit);
    let _ = std::fs::remove_dir_all(&dir);
}
