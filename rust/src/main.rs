//! `vimniscient` opens the menu; `vimniscient list` / `vimniscient run <id>` skip it.

use chrono::Local;
use clap::{Parser, Subcommand};
use vimniscient::core::cards::has_lazyvim;
use vimniscient::core::lessons::{LESSONS, two_rounds};
use vimniscient::core::progress::{Progress, today};
use vimniscient::core::{endless, evaluation, settings};
use vimniscient::system::{doctor, nvim, reminders};

#[derive(Parser)]
#[command(name = "vimniscient", about = "Absolute vim: a daily trainer.", version)]
struct Args {
    #[command(subcommand)]
    command: Option<Action>,
}

#[derive(Subcommand)]
enum Action {
    /// list the lessons
    List,
    /// endless mode without the menu
    Endless {
        /// the same tasks every time (for testing)
        #[arg(long)]
        seed: Option<String>,
    },
    /// run one lesson without the menu
    Run {
        /// lesson id, e.g. w1d1-words (see `list`)
        lesson: String,
    },
    /// notify about today's practice if any is left (for timers and hooks)
    Remind {
        /// you just started using the computer
        #[arg(long)]
        login: bool,
        /// a follow-up reminder firing
        #[arg(long)]
        check: bool,
    },
    /// how long today's routine is meant to take (15 by default)
    Minutes {
        /// set it; leave it out to see it
        minutes: Option<u32>,
    },
    /// undo the placement test
    Placement {
        #[arg(value_parser = ["reset"])]
        action: String,
    },
    /// check that Neovim and your setup work with the trainer
    Doctor,
    /// measure your progress: a test now, one later, compared
    Eval {
        #[arg(value_parser = ["pre", "post", "delayed", "report"], default_value = "report")]
        stage: String,
    },
    /// daily practice reminders through Omarchy
    Reminders {
        #[arg(value_parser = ["install", "uninstall", "status"], default_value = "status")]
        action: String,
    },
}

fn progress() -> Progress {
    Progress::open().unwrap_or_else(|error| {
        eprintln!("vimniscient: can't open your progress: {error}");
        std::process::exit(1);
    })
}

fn main() {
    let args = Args::parse();
    let lessons = &*LESSONS;
    match args.command {
        None => vimniscient::ui::run(),
        Some(Action::List) => {
            for lesson in lessons {
                println!("{:28} {}: {} ({} tasks)", lesson.id, lesson.label(), lesson.title, lesson.tasks.len());
            }
        }
        Some(Action::Remind { login, check: _ }) => println!("{}", reminders::remind(login)),
        Some(Action::Minutes { minutes }) => {
            if let Some(minutes) = minutes {
                if minutes < 1 {
                    eprintln!("error: at least one minute");
                    std::process::exit(2);
                }
                if let Err(error) = settings::set_minutes(minutes) {
                    eprintln!("vimniscient: {error}");
                }
            }
            println!("Today's routine takes about {} minutes. ({})", settings::minutes(), settings::config().display());
        }
        Some(Action::Doctor) => {
            let mut ok = true;
            for check in doctor::checks() {
                println!("{} {}: {}", check.mark(), check.name, check.detail);
                ok = ok && (check.passed || !check.required);
            }
            std::process::exit(i32::from(!ok));
        }
        Some(Action::Reminders { action }) => {
            if action == "install" {
                match reminders::install() {
                    Ok(paths) => paths.iter().for_each(|path| println!("wrote {path}")),
                    Err(error) => eprintln!("vimniscient: {error}"),
                }
                println!("Reminders on: at {} or when you start using the computer, then every {} hours until {} while practice is left.",
                         reminders::MORNING, reminders::every() / 60, reminders::day_end().format("%H:%M"));
            } else if action == "uninstall" {
                reminders::uninstall();
                println!("Reminders off.");
            }
            println!("{}", reminders::status());
        }
        Some(Action::Placement { .. }) => println!("Placement undone: {} lessons are back on the list.", progress().reset_placement()),
        Some(Action::Eval { stage }) => {
            let progress = progress();
            if stage != "report" {
                progress.record_ungraded(&nvim::run_lesson(&evaluation::lesson(&stage), false), &format!("eval-{stage}"));
            }
            println!("{}", evaluation::report(&progress));
        }
        Some(Action::Endless { seed }) => {
            let progress = progress();
            let start = progress.endless_start(endless::RESTART_BELOW);
            let open: Vec<_> = lessons.iter().filter(|l| !l.lazyvim || has_lazyvim()).cloned().collect();
            let rungs = endless::ladder(&open, start, &seed.unwrap_or_else(|| Local::now().to_rfc3339()));
            let results = nvim::run_endless(&rungs, start, endless::RAMP, endless::GAP);
            let run = endless::summary(&results, start);
            progress.record_endless(&results, &run);
            for r in &results {
                println!("{:6} {:4} {:8} {:>3}/{} keys  {}", r.task.phase, r.level, r.status, r.count, r.budget.map_or("-".to_string(), |b| b.to_string()), r.task.goal);
            }
            println!("Level {} -> {}: {} missed, {} recalled afterwards", run.start, run.level, run.missed, run.fixed);
        }
        Some(Action::Run { lesson }) => {
            let Some(lesson) = lessons.iter().find(|l| l.id == lesson) else {
                eprintln!("error: no lesson {lesson:?}; try `vimniscient list`");
                std::process::exit(2);
            };
            let mut session = lesson.clone();
            session.tasks = two_rounds(lesson, &today().to_string());
            let results = nvim::run_lesson(&session, true);
            progress().record(&results);
            for (i, r) in results.iter().enumerate() {
                let keys = if r.status == "solved" { r.count.to_string() } else { "-".to_string() };
                println!("{:2}. {:6} {:8} {keys:>3} keys (ref {})  {}", i + 1, r.task.phase, r.status, r.task.reference(), r.task.goal);
            }
        }
    }
}
