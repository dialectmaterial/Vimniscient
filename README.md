# Vimniscient

<p align="center">
<img width="427" height="442" alt="image" src="https://github.com/user-attachments/assets/0978f73d-140f-4a74-a470-a25e41fa96ad" />
</p>

Absolute vim, really. A daily trainer that runs its exercises in **your own Neovim**
(LazyVim and all), so you practise in the editor you actually use.

Each task shows a goal at the top, diffed against your text below. Edit
until they match, and the next task loads by itself. Every keystroke is
counted, and you see your keys next to the reference solution.

## Install

```bash
uv tool install --editable ~/Projects/code/vimniscient
```

Then run `vimniscient`.

Optional training wheels for everyday editing: copy
[`extras/nvim/vimniscient.lua`](extras/nvim/vimniscient.lua) to
`~/.config/nvim/lua/plugins/`. It adds:

- [hardtime.nvim](https://github.com/m4xshen/hardtime.nvim): hints about
  bad habits for the first 14 days after your first `vimniscient` run, then it
  blocks them (and the arrow keys).
- [precognition.nvim](https://github.com/tris203/precognition.nvim): shows
  where `w`, `b`, `e`, `$`, `%` … would take you. Toggle with `<leader>uV`.

## Use

| Command | What it does |
|---|---|
| `vimniscient` | Menu: today's lesson (`t`), all lessons (`j`/`k`, Enter) |
| `vimniscient list` | List the lessons |
| `vimniscient run w1d1-words` | Run one lesson directly |

Inside a lesson: `:Hint` (twice for the answer), `:Skip`, `:Reset`, `:q` to stop.
Progress is kept in `~/.local/share/vimniscient/progress.db`.

## Curriculum

| Week | Focus |
|---|---|
| 1 | Text objects, `f`/`t`, line commands, counts |
| 2 | `.`, search as a motion, `cgn`, case and numbers, insert tricks, visual mode |
| 3 | Macros, registers, marks, visual block, `:s` and `:g` *(planned)* |
| 4 | LazyVim: pickers, buffers, splits, neo-tree, LSP, surround *(planned)* |
| 5 | Omarchy, foot, tmux, shell, Zathura *(planned)* |
| 6+ | Mixed review, VimGolf, timed rounds *(planned)* |

## Writing lessons

Lessons are YAML files in `src/vimniscient/lessons/`. In `start`, `▮` marks the
cursor (it sits on the character after it):

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
    solution: ciwquick<Esc>   # reference solution; its length is the "ref" count
    hint: ciw changes the inner word under the cursor.
    ft: python                # optional filetype
```

Check that every reference solution really produces its target:

```bash
uv run python tests/check_lessons.py
```

## How it works

`vimniscient` starts `nvim` on a scratch file with
[`runner.lua`](src/vimniscient/nvim/runner.lua). Keystrokes are the `typed`
part of `vim.on_key`, meaning what you pressed before any mapping applied.
VimGolf counts keys the same way. which-key is switched off for lesson
sessions, because it replays keys, which garbles fast input and makes keys
count twice. Practice buffers also turn off autopairs, completion and
format-on-save, so plugins don't type for you.
