//! The words of the interface, and building a lesson's intro.

use crate::core::endless;
use crate::core::lessons::{Lesson, Task};
use crate::core::missions::Mission;
use crate::core::transfer;
use crate::system::vimgolf::{Challenge, SAVE_KEYS};
use std::collections::HashMap;

pub const TASK_HELP: &str = "The goal shows in the top window, your text below. When they match, the next task loads by itself. Inside Neovim: `:Hint` (twice for the answer), `:Skip`, `:Reset`, `:q` to stop.";
pub const VIMGOLF_HELP: &str = "The goal shows in the top window, your text below; it's done when they match. Inside Neovim: `:Reset` to start over, `:q` to stop.";
pub const RETRY_HELP: &str = "Skip a task you can't recall and you'll see the answer, type it once, and get it again at the end.";
pub const ROUNDS_HELP: &str = "Two rounds. **Learn**: each task with the keys to type shown. **Recall**: the same skills on new text, in another order, from memory. Only Recall counts towards your progress.";

pub fn endless_intro() -> String {
    format!("Tasks from every lesson, one after another, for as long as you like. Each one you solve climbs a level. New lessons join the mix as you climb, and the key budget shrinks: about twice the reference at first, exactly the reference by level {}.\n\nGo over the budget, `:Skip`, or ask for the answer, and it's a miss. A miss shows the answer, then you type it in with the keys shown (**Learn**). A couple of tasks later it comes back on another text, from memory (**Recall**). `:q` stops; your level is kept, and the next run starts {} levels below it.", endless::RAMP, endless::RESTART_BELOW)
}

pub fn plan_detail(step: &str) -> (&'static str, String) {
    match step {
        "cards" => ("Cards", "Type the keys for each prompt: Vim, LazyVim, Omarchy, tmux, the shell, foot, Zathura, and the habits hardtime caught. Due cards first, then up to 10 new ones.".into()),
        "drills" => ("Omarchy drills", "Do it for real on the *Vimniscient drill* window; Hyprland's events confirm each step. `h` shows the keys, `s` skips.".into()),
        "review" => ("Review", "Vim tasks from earlier days that are due again, plus a few drills for the habits hardtime keeps catching.".into()),
        "vimgolf" => ("VimGolf", "One challenge from vimgolf.com, the most played ones first, scored against the leaderboard.\n\nNot part of `t`: an extra, whenever you feel like it (or `g`).".into()),
        "quick" => ("Quick practice", "A minute or two on one skill, or navigation drills: count the lines, jump, find the `#` and delete it.\n\nNot part of `t`, and nothing is graded (or `z`).".into()),
        "transfer" => ("Choose", "Ordinary edits with no hints, where several ways work: pick yours, then compare it with another way on the results.\n\nNot part of `t`, and nothing is graded (or `x`).".into()),
        _ => ("Endless", format!("{}\n\nNot part of `t`: play it whenever you have time left.", endless_intro())),
    }
}

fn code_span(text: &str) -> String {
    if !text.contains('`') {
        return format!("`{text}`");
    }
    let longest = text.split(|c| c != '`').map(str::len).max().unwrap_or(0);
    let fence = "`".repeat(longest + 1);
    format!("{fence} {text} {fence}")
}

pub fn lesson_markdown(lesson: &Lesson, best: Option<&HashMap<usize, usize>>) -> String {
    let keys = if lesson.keys.is_empty() {
        String::new()
    } else {
        format!("**New keys** {}\n\n", lesson.keys.iter().map(|k| code_span(k)).collect::<Vec<_>>().join("  "))
    };
    let tasks = best.map_or(String::new(), |best| {
        let rows: Vec<String> = lesson.tasks.iter().enumerate().map(|(i, task)| match best.get(&i) {
            Some(keys) => format!("- {} *(✓ {keys} keys, ref {})*", task.goal, task.reference()),
            None => format!("- {}", task.goal),
        }).collect();
        format!("**{}/{} recalled**\n\n{}", best.len(), lesson.tasks.len(), rows.join("\n"))
    });
    format!("{}\n\n{keys}{tasks}", lesson.intro)
}

fn built_in(id: &str, title: String, intro: String, tasks: Vec<Task>) -> Lesson {
    Lesson { id: id.into(), title, intro, tasks, skill: "mixed".into(), ..Lesson::default() }
}

pub fn endless_lesson(start: usize, best: usize) -> Lesson {
    let record = if best > 0 { format!(" Your best is level **{best}**.") } else { String::new() };
    built_in("endless", "Endless".into(), format!("**Starting at level {start}.**{record}\n\n{}", endless_intro()), Vec::new())
}

pub fn review_lesson(tasks: Vec<Task>) -> Lesson {
    built_in("review", "Review".into(), "Tasks from earlier days that are due again. Spaced repetition brings each one back just before you'd forget it, sooner when it went badly and later when it went well.".into(), tasks)
}

pub fn quick_lesson(skill: &str, tasks: Vec<Task>) -> Lesson {
    built_in("quick", format!("Quick: {skill}"), String::new(), tasks)
}

pub fn mission_lesson(mission: &Mission) -> Lesson {
    built_in(crate::core::missions::LESSON_ID, format!("Mission: {}", mission.title), String::new(), vec![mission.task()])
}

pub fn transfer_lesson(tasks: Vec<Task>) -> Lesson {
    built_in(transfer::LESSON_ID, "Choose".into(), "Ordinary edits with no hints and no keys shown. There's more than one good way to do each: pick yours. The results show another way to do it, for comparing, not as a correction. Nothing here is graded.".into(), tasks)
}

pub fn placement_lesson(tasks: Vec<Task>) -> Lesson {
    built_in("placement", "Placement test".into(), "A short test of each skill, in a few rounds: pass and it moves further along that skill, miss and it looks earlier. A lesson counts as known when you solve its tasks without `:Hint` and in at most about 1.5× the reference keystrokes. Don't guess: `:Skip` whatever you don't know, that's what the test is for. Passing one skill says nothing about another, and `vimniscient placement reset` undoes it all.".into(), tasks)
}

pub fn vimgolf_lesson(challenge: &Challenge) -> Lesson {
    let best = challenge.best.unwrap_or(0);
    let task = Task {
        goal: format!("VimGolf: {}", challenge.title),
        start: challenge.start.clone(),
        cursor: (1, 0),
        target: challenge.target.clone(),
        solution: "—".into(),
        hint: "No hints in VimGolf. Other people's solutions are on vimgolf.com; the link is on the results screen.".into(),
        lesson_id: "vimgolf".into(),
        // The runner finishes by itself, so the reference is the best score minus saving (ZZ).
        ref_override: (best > 0).then(|| best.saturating_sub(SAVE_KEYS).max(1)),
        phase: "recall".into(),
        ..Task::default()
    };
    let scored = if best > 0 {
        format!("The best score on vimgolf.com is **{best}** ({} entries). VimGolf scores include `ZZ` to save, so your score is your keys + {SAVE_KEYS}.", challenge.entries)
    } else {
        String::new()
    };
    built_in("vimgolf", format!("VimGolf: {}", challenge.title), format!("Today's challenge from [vimgolf.com]({}): make the text match, in as few keystrokes as you can. {scored}", challenge.url()), vec![task])
}
