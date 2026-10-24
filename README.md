# Vimniscient

<p align="center">
<img width="427" height="442" alt="Vimniscient" src="https://github.com/user-attachments/assets/0978f73d-140f-4a74-a470-a25e41fa96ad" />
</p>

**Get fluent in Vim with about fifteen minutes of practice a day, in your own Neovim.**

You've done `vimtutor`, you can get around, and you still reach for `jjjj`
and Backspace. Vimniscient is the next step. It gives you real editing tasks
that run in the Neovim you use every day, with your config, plugins and
colours. A reference solution shows you a shorter way, and spaced repetition
brings each skill back until it sticks.

<p align="center"><img src="docs/lesson.png" alt="A lesson in Neovim: the goal at the top, your text below, keystrokes counted live" width="820"></p>

## How a lesson works

Each task shows the goal at the top and your text below, with the
differences highlighted. Edit until they match, and the next task loads by
itself. There's nothing to submit, and any way of getting there counts.

Your keystrokes are counted the same way [VimGolf](https://www.vimgolf.com)
counts them, and afterwards you see your keys next to the reference
solution. If `ciwbuf<Esc>..` took you 14 keys and the reference does it in
10, you'll see how.

Stuck? Type `:Hint` (twice for the answer). `:Skip` and `:Reset` do what
they say, and `:q` stops.

## Quick start

You need Linux (macOS should work but is untested), [Neovim](https://neovim.io) 0.10 or newer,
Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/dialectmaterial/Vimniscient
vimniscient
```

1. Press **`p`** for the placement test. It gives you two tasks from every
   lesson and skips the ones you already know. `:Skip` whatever you don't.
2. From then on, press **`t`** once a day.

Your progress is kept in `~/.local/share/vimniscient/`. Vimniscient doesn't
change your Neovim config.

## What you'll learn

37 lessons and 194 tasks over six weeks, one lesson a day:

| Week | Topics |
|---|---|
| 1 | Text objects (`ciw`, `da"`, `dap`), `f`/`t`, line commands, counts |
| 2 | The dot command, search as a motion, `cgn`, case and numbers, getting into insert mode well, visual mode |
| 3 | Macros, registers, marks, visual block, `:s` and `:g` |
| 4 | Ranges (`:m`, `:t`), `:sort` and shell filters, patterns, `:norm`, more motions, indenting |
| 5 | [LazyVim](https://www.lazyvim.org)'s text objects (arguments, any quote or bracket, functions, classes, sub-words) and comments. Only shown if you use LazyVim |
| 6 | Real edits on code, notes and data, each mixing several tools |

Each week ends with a review day. Every reference solution is tested: the
plain-Vim ones in `nvim --clean`, and all of them typed at full speed into a
LazyVim setup.

## A day with Vimniscient

`t` runs the daily routine:

1. **Cards**: short prompts ("Change everything inside the quotes"), where you
   type the keys (`ci"`). The ones that are due come first, then up to 10 new ones.
2. **Review**: tasks from earlier days that are due again.
3. **Today's lesson**.
4. **[VimGolf](https://www.vimgolf.com)**: one real challenge a day, starting
   with the most played ones. You play it in your Neovim, and your score is
   compared with the site's leaderboard.

Cards and tasks share one spaced-repetition schedule, like Anki. Whatever
went well comes back later, and whatever you forgot comes back tomorrow.

<p align="center"><img src="docs/home.png" alt="The home screen: today's routine, the lessons, the selected lesson and your progress" width="820"></p>

The home screen shows everything at once: today's routine, the lessons
(✓ solved, ◐ started, ○ skipped by the placement test), the selected
lesson, and your progress with a keystroke-efficiency graph.

| Key | Action |
|---|---|
| `t` | Run today's routine |
| `Enter` | Start the selected step or lesson |
| `Tab`, `j`/`k` | Move between panes and through lists |
| `c` / `g` / `p` | Cards / VimGolf / placement test |
| `s` | Stats |
| `q` | Quit |

## It adapts to your setup

| You have | You get |
|---|---|
| Neovim | Weeks 1–4 and 6, Vim and shell cards, VimGolf |
| [LazyVim](https://www.lazyvim.org) | Week 5, plus LazyVim cards whose names and keys are read from your own config |
| [hardtime.nvim](https://github.com/m4xshen/hardtime.nvim) | Your bad habits become cards ("You typed `2dd`. What's shorter?"). When you lean on `hjkl` a lot, review brings back the motion lessons |
| [Omarchy](https://omarchy.org) / Hyprland | Cards for every desktop and tmux keybinding (read live), and live drills (`d`): "send this window to workspace 9 and fetch it back", checked through Hyprland's events |
| foot, Zathura | Cards for their keys |

### Optional: practice while you work

[`extras/nvim/vimniscient.lua`](extras/nvim/vimniscient.lua) is a
[lazy.nvim](https://github.com/folke/lazy.nvim) plugin spec. Copy it to
`~/.config/nvim/lua/plugins/` if you want:

- [hardtime.nvim](https://github.com/m4xshen/hardtime.nvim): hints when you
  do things the slow way, for your first two weeks. After that it blocks
  them, along with the arrow keys.
- [precognition.nvim](https://github.com/tris203/precognition.nvim): shows
  where `w`, `b`, `e`, `$` … would take you. It starts hidden; toggle it with
  `<leader>uV`.

## Questions

**Why not just use vimtutor, Vim Adventures or VimGolf?** Use them! vimtutor
teaches the basics, and this picks up after it. Vimniscient runs in your real
editor, schedules what you need to repeat, and turns VimGolf into a daily
habit.

**Does it work with my plugins?** Yes, that's the point. For a lesson it only
turns off what would type for you (autopairs, completion, format-on-save),
plus [which-key](https://github.com/folke/which-key.nvim), which replays your
keys and would make them count twice.

**My answer to a card was right but got marked wrong.** Common notations are
accepted (`<C-a>`, `ctrl-a`, `^a`; `<leader>ff`, `space ff`). If yours still
fails, press `o` ("I was right").

## Writing lessons

Lessons are YAML files in [`src/vimniscient/lessons/`](src/vimniscient/lessons).
`▮` marks where the cursor starts:

```yaml
week: 1
day: 1
title: Word text objects
intro: |
  Shown before the lesson starts.
keys: [ciw, daw]
tasks:
  - goal: 'Change "slow" to "quick".'
    start: |-
      The sl▮ow brown fox.
    target: |-
      The quick brown fox.
    solution: ciwquick<Esc>   # the reference; its length is the "ref" count
    hint: ciw changes the inner word under the cursor.
    ft: python                # optional filetype
```

More details:
- `␣` stands for a space that must survive editors stripping trailing whitespace.
- `review: true` marks a review day (the placement test skips it).
- `lazyvim: true` marks lessons that need LazyVim.
- Indented text needs an indentation indicator (`|2-`), or YAML strips the leading spaces.

Before sending a lesson, check that every solution really produces its target:

```bash
uv run python tests/check_lessons.py            # plain-Vim lessons, in nvim --clean
uv run python tests/check_lessons.py --lazyvim  # LazyVim lessons, in your own config
uv run python tests/check_answers.py            # card answers written different ways
uv run python tests/live_lessons.py --all       # types every solution into the real runner (needs tmux)
```

## How it works

`vimniscient` is a [Textual](https://textual.textualize.io) app. A lesson
starts `nvim` on a scratch file with
[`runner.lua`](src/vimniscient/nvim/runner.lua). It shows the goal in a
diffed split, checks your text after every change, and counts the `typed`
part of `vim.on_key`: what you pressed, before any mapping applied.

## License

[AGPL-3.0](LICENSE)
