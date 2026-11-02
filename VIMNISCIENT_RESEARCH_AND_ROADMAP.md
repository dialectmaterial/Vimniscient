# Vimniscient — Where It Is and Where It Goes Next

> **Repository:** https://github.com/dialectmaterial/Vimniscient
> **Updated:** 2 November 2026 (research 26 Oct · audit 29 Oct · Rust port 30 Oct · review fixes 2 Nov)
> **Status:** Living document. Directions in §4 are proposals until you pick them; then
> they're built one reviewable slice at a time.

**Central question (unchanged):** how can Vimniscient help a learner *remember* a
command, *execute* it fluently, and *choose* it well in unfamiliar real editing,
rather than solve a familiar puzzle in few keystrokes?

---

## 0. Where we are (2 November 2026)

**Version 1.0.1** is released (GitHub, PyPI, crates.io). It's one Rust binary; Python
is gone. `main` has two more commits after the review on 2 November (see §7). They
aren't in a release yet.

| Area | What exists | Gaps |
| --- | --- | --- |
| Lessons | 37 lessons over 6 weeks (7, 7, 7, 7, 6, 3), 196 tasks, 575 written texts, Learn then Recall | Week 6 has 3 lessons. Nothing is planned for after the last lesson |
| Variation | 37 generator kinds on 36 tasks, all in weeks 1–4 | Weeks 5–6 have no generators. 6 tasks have only two texts and no generator |
| Cards | vim 84, lazyvim 33, zathura 25, shell 16, foot 12. Omarchy, tmux and your hardtime habits are read live | |
| Drills | 9 Omarchy drills on Hyprland events | |
| Extras | Choose (19 hint-free tasks), 4 multi-file missions, Quick practice, Endless, VimGolf | Quick practice and missions have never been played by hand |
| Adaptation | Placement by skill, a daily time budget (`minutes`), 10 skill families | No mastery per skill: progress is per task and per lesson |
| Feedback | Mnemonic hooks after an answer, 3 rules about your own keys | |
| Measurement | Time per task, `vimniscient eval pre/post/delayed` | The pre-test was only partly taken (§1) |
| Quality | `cargo test` (18 tests, golden files), every solution played in real Neovim (`check_neovim.py`), tmux live runs (`live.py`), CI on every push, releases gated on tests | Plugin compatibility is still only tested on your own setup |

---

## 1. Evidence from real use (24 Oct – 2 Nov, one learner)

- **Habit:** active every day from 24 to 31 October (8 of 8 days). Nothing yet on
  1 and 2 November.
- **Lessons:** 9 done (week 1 and the first two of week 2). The next is
  `w2d3-cgn`. At about one a day, the last lesson comes up in late November.
- **Recall:** 138 solved and 5 quit, at 1.09× the reference keys on average,
  11.1 s a task.
- **Cards:** from 37% right (24–28 Oct) to **88% on 31 Oct** (22 of 25), after the
  card introductions and lesson gating. But **32 of 52 cards are due now**, and 30
  have lapsed at least once: the backlog grows when a day is missed.
- **Drills:** 8 drills started, mostly 11–12 s each, few skips.
- **Endless:** two runs, to level 19 and 32.
- **VimGolf:** 0 of 5 solved. It stays optional.
- **Not used yet:** Quick practice, missions, and placement (you started at the
  beginning). Choose was played once (4 tasks).
- **Eval:** the pre-test on 30 Oct recorded 4 of its 8 tasks, 3 solved. That isn't
  a full baseline yet.
- **Hardtime** can start blocking on 21 November at the earliest: 28 days after
  the start, and once `w2d7-review` is done.

---

## 2. Ground rules

1. The current code is authoritative. Re-check a claim here before acting on it.
2. Build in small, separately reviewable slices. Each one passes `cargo test`,
   `cargo clippy -- -D warnings`, `python3 tests/check_neovim.py` and, when it
   touches lessons in Neovim, `python3 tests/live.py`. CI runs the first two.
3. Preserve existing progress data, your own Neovim and LazyVim setup,
   keyboard-only use, and the public CLI. Schema changes must be additive.
4. Keep the core deterministic and offline. No LLM, account, telemetry or
   leaderboard is needed to train.
5. Practice texts are about their keys (`mnemonics.yaml`). Every task has at
   least two. Memory science stays in lesson intros, traceable to
   `lessons/sources.md`. Code tasks keep their mnemonics in names and docstrings.
   Week 6 and the week 5 review code stay realistic on purpose.
6. **Task ids are positions.** New tasks go at the end of a lesson. Moving a task
   hands its review history to another one, and `tests/golden/task_ids.json` makes
   that fail the tests.
7. Visual changes are shown as previews and approved before they land.

---

## 3. Open questions the next weeks should answer

| Question | How we'll know | Decides |
| --- | --- | --- |
| Does the daily habit survive past the novelty? | Days active in November, now that the course is past week 1 | Whether reminders, budget or cards need changing |
| Does the card backlog shrink or pile up? | Due cards per day, and accuracy after a missed day | Proposal B2 |
| Do Quick practice, missions and drills work in real use? | Playing each one at least once | Bug fixes before new features |
| Does the training transfer to unfamiliar edits? | A full `eval pre` now, `post` after the course, `delayed` a few weeks later | Whether the method works at all (§5) |
| Which skills are weakest? | Recall time and keys per skill family | Proposals B1 and C1 |

---

## 4. Where to take it next: proposals

Effort is in *sessions* (one working block of a few hours). **Rec.** marks what I'd
do first. Nothing here starts until you choose it.

### A. Now: ship and use what's built

| # | Proposal | Why | Effort |
| --- | --- | --- | --- |
| A1 **Rec.** | **Release 1.0.2** with the 2 November fixes | 1.0.1 users can still hit the drill bug that blanks and freezes the app | 0.1 |
| A2 **Rec.** | **Take the full `eval pre`** (all 8 tasks) | Without a baseline the evaluation can't say anything | You, 15 min |
| A3 | Play Quick practice, a mission and a drill session once each, and fix what turns up | None has been played by hand since the Rust port | 0.25–0.5 |

### B. The learning model

| # | Proposal | Why | Effort |
| --- | --- | --- | --- |
| B1 **Rec.** | **Mastery per skill family.** Combine Recall success, keys against the reference, and time per skill into one view on Stats, and let Quick practice offer the weakest skill first | The audit's open point B. Every lesson already has a skill tag, but progress stops at the lesson | 1 |
| B2 | **Cards after a missed day.** Spread a backlog over a few days instead of letting it fill the budget, and show the backlog itself on Today | 32 of 52 due now. The budget already caps what's asked, but not what waits | 0.5 |
| B3 | **Endless feeds reviews.** A task missed in Endless becomes due for review (it's graded nowhere today) | You answered "idk" on 29 Oct. Decide once Endless gets regular use | 0.5 |

### C. Content

| # | Proposal | Why | Effort |
| --- | --- | --- | --- |
| C1 **Rec.** | **After the course.** When the last lesson is done, the lesson step becomes the weakest skill's practice (B1), with Choose and a mission in rotation | At one lesson a day you finish in late November. Today the step just says "all done" | 1 |
| C2 | **Finish week 6** (3 of 7 days): more real edits on notes, code and data | Week 6 is the closest the lessons get to real editing | 1–1.5 |
| C3 | **Generators for weeks 5–6** (text objects, arguments, functions) | Recall there only has written texts | 0.75 |
| C4 | **A third text** for the 6 tasks that still have two | Ground rule 5's spirit | 0.25 |
| C5 | More Choose tasks and missions, unlocked through weeks 4–6 | Transfer is the outcome least trained so far | 0.5–1 |

### D. Feedback

| # | Proposal | Why | Effort |
| --- | --- | --- | --- |
| D1 | **New strategy rules from your own keys.** Look through the 138 stored Recall solutions for patterns the 3 rules miss | Rules should come from real habits, not guesses | 0.5–1 |

### E. Reach (only if you want strangers to use it)

| # | Proposal | Why | Effort |
| --- | --- | --- | --- |
| E1 | Builds for aarch64 Linux and macOS | The release has only x86-64 Linux | 0.5 |
| E2 | Test against a stock LazyVim and a plain Neovim in CI | Compatibility is only tested on your setup | 0.5–1 |
| E3 | Without Omarchy, hide what needs it more gracefully | Drills and reminders are Omarchy-only | 0.25 |

**Suggested order:** A1 → A2 → A3, two weeks of use, then B1 → C1. The rest follows
what §3 shows.

---

## 5. Learning-science framing

Keep three outcomes apart:
1. **Retrieval:** do you remember the command after a delay?
2. **Fluency:** can you execute it quickly and accurately? (Timing measures this.)
3. **Transfer and strategy:** can you choose well in unfamiliar edits?

Spacing, retrieval practice, interleaving and varied practice are a plausible
foundation (`lessons/sources.md`). But findings on declarative memory don't prove
the best schedule for motor skills, so "daily practice builds muscle memory" is a
hypothesis. `vimniscient eval` tests it: a pre-test on tasks from no lesson, a
post-test after the course, and a delayed one, comparing accuracy, time and keys.
The data stays local.

---

## 6. Explicitly not doing (for now)

- **Leaderboards, RPG campaigns, badges, a narrative world:** they distract from
  training and cost upkeep.
- **An LLM tutor or AI feedback:** rule-based feedback comes first. Any AI would
  be optional and never the judge of correctness.
- **FSRS:** keep SM-2 until the data shows it falls short.
- **Telemetry or online accounts:** progress stays local.
- **Browser demo, translations, difficulty presets, replayed solutions, a
  `:Vimniscient` command in Neovim, a beginner path, community features:** dropped
  on 30 October.
- **Lowercase `:hint`/`:skip`/`:reset`:** declined.
- **Rewriting the lesson system:** the YAML lessons and Learn/Recall stay.

**Failure modes to keep avoiding:** replacing working infrastructure before a real
limit shows · optimising for the reference count and teaching brittle VimGolf
tricks · treating one solved task as proof of broad skill · treating slower,
thoughtful editing as failure (time is shown, never graded) · hints that assume one
correct style · touching your real files, or logging keys without consent · making
external services mandatory · breaking themes, the LazyVim/Omarchy integration or
progress history.

---

## 7. History

| Date | Milestone |
| --- | --- |
| 24 Oct | Stages 1–4: Textual app, Neovim runner, weeks 1–6, cards, SRS, placement, VimGolf, habits, drills, Endless |
| 26 Oct | Research brief: six problems (P1–P6) and three missing capabilities (A–C) |
| 29 Oct | Audit of the brief against the code; timing, the daily budget, card introductions; v0.2.0, the first release |
| 30 Oct | Every audit point acted on: variation (575 texts, 37 generator kinds), diagnostics, placement by skill, Choose, missions, Quick practice, `doctor`, `eval`. Filler texts removed |
| 30 Oct | **Rust port, v1.0.0**: on screen in 75 ms instead of 425, 12 MB of memory instead of 50, golden files kept from the Python version. A copy of the old database is at `~/.local/share/vimniscient/progress.before-rust.db` |
| 30 Oct | v1.0.1: highlights span the row, the graph fills its pane |
| 2 Nov | Code review and fixes (unreleased): drill events no longer drop the screen; reminders after an unlock wait; private temp folders; timeouts; placement can be stopped; task ids guarded; CI with releases gated on tests |

**Where the 26 October problems stand:** P1 variation and P2 timing are done. P3
diagnostics has three rules (D1 continues it). P4 placement is by skill now. P5 SRS
caps are replaced by the daily budget, and Endless is still apart from SRS (B3). P6
strategy is covered by Choose and missions. Of the missing capabilities, A
(multi-file missions) and C (`doctor`) are done; B, mastery per skill, is open (B1).

**Inspiration:** Vim Adventures, VimHero, VimGolf, vim-dojo.nvim, vim-be-better,
Vim Mastery, VimVenture, OpenVim, VimGenius, vim-be-good, Learn Vim. Vimniscient's
edge is practice in your real Neovim plus long-term learning support.
