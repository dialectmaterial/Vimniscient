//! Made-up Hyprland events for every drill: the steps tick off, and look-alike events
//! (another window, another workspace) don't count.

use vimniscient::core::drills::{DrillRun, grade, load_drills};
use vimniscient::core::srs;

const D: &str = "aaa111";
const O: &str = "bbb222";
const N: &str = "ccc333";

fn play(id: &str, lines: &[String]) -> bool {
    let drill = load_drills().into_iter().find(|d| d.id == id).unwrap_or_else(|| panic!("no drill {id}"));
    let mut run = DrillRun::new(drill, D.into(), "2".into());
    for line in lines {
        run.feed(line);
    }
    run.finished()
}

#[test]
fn every_drill_finishes_on_the_right_events() {
    let good: Vec<(&str, Vec<String>)> = vec![
        ("focus", vec![format!("activewindowv2>>{D}"), format!("activewindowv2>>{O}"), format!("activewindowv2>>{D}")]),
        ("float", vec![format!("changefloatingmode>>{O},1"), format!("changefloatingmode>>{D},1"), format!("changefloatingmode>>{D},0")]),
        ("fullscreen", vec![format!("activewindowv2>>{O}"), "fullscreen>>1".into(), "fullscreen>>0".into(), format!("activewindowv2>>{D}"), "fullscreen>>1".into(), "fullscreen>>0".into()]),
        ("full-width", vec![format!("activewindowv2>>{D}"), "fullscreen>>1".into(), "fullscreen>>0".into()]),
        ("pop", vec![format!("pin>>{D},1"), format!("pin>>{D},0")]),
        ("workspace-visit", vec!["workspacev2>>3,3".into(), "workspacev2>>9,9".into(), "workspacev2>>2,2".into()]),
        ("workspace-move", vec![format!("movewindowv2>>{O},9,9"), format!("movewindowv2>>{D},9,9"), "workspacev2>>9,9".into(), format!("movewindowv2>>{D},2,2")]),
        ("terminal", vec![format!("openwindow>>{N},2,foot,dima@host:~"), format!("closewindow>>{O}"), format!("closewindow>>{N}")]),
        ("close", vec![format!("closewindow>>{O}"), format!("closewindow>>{D}")]),
    ];
    assert_eq!(good.len(), load_drills().len());
    for (id, lines) in &good {
        assert!(play(id, lines), "{id} got stuck");
    }
}

#[test]
fn look_alike_events_do_not_count() {
    let bad: Vec<(&str, Vec<String>)> = vec![
        ("focus", vec![format!("activewindowv2>>{D}"), format!("activewindowv2>>{D}")]),
        ("float", vec![format!("changefloatingmode>>{O},1"), format!("changefloatingmode>>{O},0")]),
        ("fullscreen", vec![format!("activewindowv2>>{O}"), "fullscreen>>1".into(), "fullscreen>>0".into()]),
        ("workspace-visit", vec!["workspacev2>>9,9".into(), "workspacev2>>4,4".into()]),
        ("terminal", vec![format!("openwindow>>{N},2,foot,x"), format!("closewindow>>{O}")]),
    ];
    for (id, lines) in &bad {
        assert!(!play(id, lines), "{id} finished on events that shouldn't count");
    }
}

#[test]
fn grades_follow_the_time() {
    assert_eq!(grade(5.0, false, false), srs::EASY);
    assert_eq!(grade(20.0, false, false), srs::GOOD);
    assert_eq!(grade(40.0, false, false), srs::HARD);
    assert_eq!(grade(5.0, true, false), srs::HARD);
    assert_eq!(grade(5.0, false, true), srs::AGAIN);
}
