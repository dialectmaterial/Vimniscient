//! The placement test reads a quit round as nothing tried, not as a round of misses.

use vimniscient::core::lessons::LESSONS;
use vimniscient::core::placement::{Search, tried};
use vimniscient::core::results::TaskResult;

#[test]
fn quitting_a_round_moves_nothing() {
    let mut search = Search::new(&LESSONS, Some(false));
    let round = search.round();
    let quit: Vec<TaskResult> = round.iter().map(|t| TaskResult::new(t, "quit", "", 0, 0)).collect();
    assert!(!tried(&quit));
    search.update(&quit);
    let again: Vec<String> = search.round().iter().map(|t| t.item_id()).collect();
    assert_eq!(again, round.iter().map(|t| t.item_id()).collect::<Vec<_>>(), "a quit round counted as misses");
    assert!(search.known().is_empty());

    // a real miss still looks earlier
    let missed: Vec<TaskResult> = round.iter().map(|t| TaskResult::new(t, "skipped", "", 0, 0)).collect();
    assert!(tried(&missed));
    search.update(&missed);
    assert_ne!(search.round().iter().map(|t| t.item_id()).collect::<Vec<_>>(), again);
}
