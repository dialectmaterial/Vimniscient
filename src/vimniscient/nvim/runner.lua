-- Runs one Vimniscient lesson inside the user's own Neovim.
--
-- Started as `nvim -i NONE practice.txt -S runner.lua` with
-- $VIMNISCIENT_SESSION pointing at a JSON file:
--   { title, result_path, tasks = { { goal, start, cursor, target, ref, hint, solution, ft, label, show } } }
-- `label` heads the goal window (LEARN 2/6, RECALL 2/6); `show` is set during
-- the Learn round and puts the keys to type in the practice window.
-- With session.retry, skipping a Recall task shows its answer, has you type it
-- (a Learn copy, next) and asks for it again on the task's next text (`again`)
-- at the end. Every task carries `n`, its place in the lesson, and the extra
-- ones `extra` (learn | recall), so results can be matched up.
-- The goal is shown in a read-only split above, diffed against the practice
-- buffer. A task is solved as soon as the buffer matches the target in normal
-- mode; results go to result_path when Neovim exits.
--
-- Keystrokes are the `typed` part of vim.on_key, i.e. what was pressed before
-- any mapping applied (as VimGolf counts them).
--
-- Endless mode (session.endless = { pool, rungs, level, ramp, gap }, see
-- endless.py) starts with no tasks and adds them as it goes: the next rung of
-- the climb, or a Learn copy and later a Recall of a task that was missed. A
-- climb or recall task has a key budget; going over it is a miss.

-- luanil: a JSON null becomes nil (vim.NIL would be truthy)
local session = vim.json.decode(io.open(os.getenv("VIMNISCIENT_SESSION")):read("*a"),
  { luanil = { object = true, array = true } })
local tasks = session.tasks

-- Looks: one centred column, like the app's card screen (see the CSS in
-- app.py): a rounded frame titled with the lesson, a progress bar, the goal in
-- bold, the goal text and your text in two boxes, feedback under them, and the
-- commands along the bottom. The boxes are floats over the frame; the window
-- the practice file opened in stays behind them, blank.
local function scratch()
  local buf = vim.api.nvim_create_buf(false, true)
  vim.bo[buf].bufhidden = "wipe"
  return buf
end

local back_win = vim.api.nvim_get_current_win()
local practice_buf = vim.api.nvim_get_current_buf()
vim.bo[practice_buf].bufhidden = "hide"
vim.api.nvim_win_set_buf(back_win, scratch())
local goal_buf = scratch()
local frame_buf = scratch()
local keys_buf = scratch()

-- The app's theme colours when it sent them, else the colourscheme's own.
local colors = session.colors
local function hl(name, link, fg, extra)
  local spec = colors and vim.tbl_extend("force", { fg = colors[fg], bg = colors.background }, extra or {})
    or { link = link }
  vim.api.nvim_set_hl(0, name, spec)
end
local function set_colors()
  hl("VimniscientNormal", "NormalFloat", "foreground")
  hl("VimniscientFrame", "FloatBorder", "primary")
  hl("VimniscientBox", "FloatBorder", "panel")
  hl("VimniscientTitle", "Title", "primary", { bold = true })
  hl("VimniscientMuted", "Comment", "muted")
  hl("VimniscientStrong", "Bold", "foreground", { bold = true })
  hl("VimniscientTodo", "NonText", "panel")
  hl("VimniscientRight", "DiagnosticOk", "success")
  hl("VimniscientWrong", "DiagnosticError", "error")
  hl("VimniscientAccent", "Special", "accent")
end
set_colors()
vim.api.nvim_create_autocmd("ColorScheme", { callback = set_colors })

local look = "Normal:VimniscientNormal,NormalFloat:VimniscientNormal,FloatTitle:VimniscientTitle,"
  .. "FloatFooter:VimniscientMuted,EndOfBuffer:VimniscientNormal"
vim.wo[back_win].winhighlight = look
vim.wo[back_win].fillchars = "eob: "
vim.wo[back_win].number = false
vim.wo[back_win].relativenumber = false
vim.wo[back_win].signcolumn = "no"
vim.wo[back_win].cursorline = false

local function float(buf, enter, config)
  local win = vim.api.nvim_open_win(buf, enter, vim.tbl_extend("keep", config,
    { relative = "editor", row = 0, col = 0, width = 10, height = 1, style = "minimal" }))
  vim.wo[win].winhighlight = look .. ",FloatBorder:" .. (config.border and "VimniscientBox" or "VimniscientNormal")
  return win
end
local frame_win = float(frame_buf, false, { border = "rounded", focusable = false, zindex = 40 })
vim.wo[frame_win].winhighlight = look .. ",FloatBorder:VimniscientFrame"
local keys_win = float(keys_buf, false, { focusable = false, zindex = 40 })
local goal_win = float(goal_buf, false, { border = "rounded", zindex = 45 })
local practice_win = float(practice_buf, true, { border = "rounded", zindex = 45 })
vim.wo[practice_win].winhighlight = look .. ",FloatBorder:VimniscientFrame"
for _, win in ipairs({ goal_win, practice_win }) do
  vim.wo[win].foldcolumn = "1" -- a space of padding, as in the app's input box
  vim.wo[win].wrap = false
end

-- The frame stands in for the statusline and tabline; plugins may set them
-- again while starting up, so they're put back once that's done.
local function quiet_ui()
  vim.o.laststatus = 0
  vim.o.showtabline = 0
  vim.o.ruler = false
end
quiet_ui()
vim.api.nvim_create_autocmd("User", { pattern = "VeryLazy", callback = function() vim.defer_fn(quiet_ui, 50) end })
vim.defer_fn(quiet_ui, 300)

-- Keyboard only: a click would move the cursor without a keystroke counted.
vim.o.mouse = ""

-- Don't let session plugins remember the throwaway practice file.
pcall(function() require("persistence").stop() end)
-- precognition's hints lose keys typed fast after an operator (`cia` + text).
pcall(function() require("precognition").hide() end)
-- which-key swallows keys and feeds them back, which garbles fast operator
-- input and reports keys twice. It's off for this session only.
pcall(function()
  vim.list_extend(require("which-key.config").disable.bt, { "", "nofile" })
  require("which-key.buf").clear()
end)
-- hardtime would log the lessons' own keys as bad habits (and block them once
-- it blocks). It turns itself on 500ms after loading, unless `enabled` is off.
pcall(function()
  require("hardtime.config").config.enabled = false
  require("hardtime").disable()
end)

-- Text as lines of { text, highlight } chunks, wrapped at word boundaries.
local function wrap(chunks, width)
  local lines, line, used = {}, {}, 0
  for _, chunk in ipairs(chunks) do
    local text, group = chunk[1], chunk[2]
    if text == "\n" then
      table.insert(lines, line)
      line, used = {}, 0
    else
      for space, word in text:gmatch("(%s*)(%S+)") do
        local w = vim.fn.strdisplaywidth(word)
        if used > 0 and used + #space + w > width then
          table.insert(lines, line)
          line, used, space = {}, 0, ""
        end
        table.insert(line, { space .. word, group })
        used = used + #space + w
      end
      local trailing = text:match("%s+$")
      if trailing and used > 0 then
        table.insert(line, { trailing, group })
        used = used + #trailing
      end
    end
  end
  table.insert(lines, line)
  return lines
end

-- What the frame says under the boxes: how a task went, a hint, what's next.
-- It stays until the first key typed on the task after it.
local feedback = {}
local redraw -- defined with the layout below

local function tell(chunks)
  feedback = chunks
  if redraw then
    redraw()
  end
end

local MUTED, STRONG, RIGHT, WRONG, ACCENT, TITLE =
  "VimniscientMuted", "VimniscientStrong", "VimniscientRight", "VimniscientWrong", "VimniscientAccent", "VimniscientTitle"

-- What the keys stand for, one per line: dim after a solve, accent after a miss.
local function why(task, group)
  local out = {}
  for _, hook in ipairs(task.why or {}) do
    vim.list_extend(out, { { "\n" }, { hook, group } })
  end
  return out
end

local results = {}
for i = 1, #tasks do
  results[i] = { status = "unseen", keys = "", count = 0, hints = 0, n = tasks[i].n }
end

local endless = session.endless
local climb = endless and { level = endless.level, rung = 0, pending = {} }

-- About twice the reference at level 1, the reference itself from level `ramp` on.
local function budget(ref)
  local slack = math.max(0, 1 - (climb.level - 1) / endless.ramp)
  return ref + math.ceil(ref * slack) + (slack > 0 and 1 or 0)
end

-- Version v of a pool task, as a climb, learn or recall task.
local function endless_task(id, v, phase)
  local versions = endless.pool[id]
  v = v % #versions
  local task = vim.deepcopy(versions[v + 1])
  task.id, task.v, task.phase, task.level = id, v, phase, climb.level
  if phase == "learn" then
    task.label, task.show = "LEARN", task.solution
  else
    task.budget = budget(task.ref)
    task.label = phase == "recall" and "RECALL" or string.format("LEVEL %d", climb.level)
  end
  return task
end

local function add_task(task)
  table.insert(tasks, task)
  table.insert(results, { status = "unseen", keys = "", count = 0, hints = 0, id = task.id, v = task.v,
    phase = task.phase, level = task.level, budget = task.budget })
end

-- A recall that's due comes first, then the next rung (wrapping round at the end).
local function endless_next()
  for i, p in ipairs(climb.pending) do
    if p.after <= climb.rung then
      table.remove(climb.pending, i)
      return endless_task(p.id, p.v, "recall")
    end
  end
  climb.rung = climb.rung + 1
  local rung = endless.rungs[(climb.rung - 1) % #endless.rungs + 1]
  return endless_task(rung.id, rung.v, "climb")
end

local current = 0
local state = { keys = {}, done = true, hints = 0 }

local function tokens(s)
  local out, i = {}, 1
  while i <= #s do
    local tok = s:match("^<[^<>%s]+>", i)
    if not tok then
      local c = s:byte(i)
      tok = s:sub(i, i + (c < 0x80 and 0 or c < 0xE0 and 1 or c < 0xF0 and 2 or 3))
    end
    table.insert(out, tok)
    i = i + #tok
  end
  return out
end

local function ignored(key)
  return key:find("Mouse") or key:find("Drag") or key:find("Release") or key:find("ScrollWheel")
    or key:find("^<Focus") or key == "<Ignore>" or key == "<Cmd>"
end

-- Keys typed since the current task loaded, minus :Hint/:Skip/:Reset.
local function task_keys()
  local s = table.concat(state.keys)
  for _, cmd in ipairs({ "Hint", "Skip", "Reset" }) do
    s = s:gsub(":" .. cmd .. "<CR>", ""):gsub(":" .. cmd .. "$", "")
  end
  local kept = {}
  for _, tok in ipairs(tokens(s)) do
    if not ignored(tok) then
      table.insert(kept, tok)
    end
  end
  return table.concat(kept), #kept
end

local MODES = { n = "NORMAL", i = "INSERT", v = "VISUAL", V = "V-LINE", ["\22"] = "V-BLOCK", R = "REPLACE",
  c = "COMMAND", o = "PENDING", s = "SELECT", t = "TERMINAL" }
local BAR = 40 -- as wide as the app's progress bar
local frame_ns = vim.api.nvim_create_namespace("vimniscient-frame")

-- Write chunk lines into a buffer, highlighting each chunk.
local function paint(buf, lines)
  local text = {}
  for i, line in ipairs(lines) do
    text[i] = table.concat(vim.tbl_map(function(c) return c[1] end, line))
  end
  vim.bo[buf].modifiable = true
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, text)
  vim.bo[buf].modifiable = false
  vim.api.nvim_buf_clear_namespace(buf, frame_ns, 0, -1)
  for i, line in ipairs(lines) do
    local col = 0
    for _, c in ipairs(line) do
      if c[2] and #c[1] > 0 then
        vim.api.nvim_buf_set_extmark(buf, frame_ns, i - 1, col, { end_col = col + #c[1], hl_group = c[2] })
      end
      col = col + #c[1]
    end
  end
end

function redraw()
  local task = tasks[current]
  if not task or not vim.api.nvim_win_is_valid(frame_win) then
    return
  end
  local _, count = task_keys()
  local columns, rows = vim.o.columns, vim.o.lines - vim.o.cmdheight - 1 -- the key line takes one
  local outer = math.min(columns - 2, 80)
  local width = outer - 2 - 4 -- inside the border and two columns of padding each side
  local box = width - 2

  local lines = { {} }
  if not endless then
    local done = state.done and current or current - 1
    local filled = math.floor(BAR * done / #tasks + 0.5)
    table.insert(lines, { { string.rep("━", filled), TITLE }, { string.rep("━", BAR - filled), "VimniscientTodo" } })
    table.insert(lines, {})
  end
  vim.list_extend(lines, wrap({ { task.goal, TITLE } }, width))
  if task.show and task.show ~= "" then
    table.insert(lines, { { "type  ", MUTED }, { task.show, STRONG } })
  end
  table.insert(lines, {})

  local start_lines = #vim.api.nvim_buf_get_lines(practice_buf, 0, -1, false)
  local goal_h, practice_h = math.max(1, #task.target), math.max(1, #task.target, start_lines)
  local said = wrap(feedback, width)
  local fixed = #lines + 4 + 1 + math.max(3, #said) + 1 -- two box borders, then feedback with a line around it
  local over = fixed + goal_h + practice_h - (rows - 2)
  if over > 0 then
    local cut = math.min(over, math.max(0, goal_h - 3))
    goal_h, over = goal_h - cut, over - cut
    practice_h = math.max(3, practice_h - math.max(0, over))
  end

  local goal_row = #lines
  for _ = 1, goal_h + 2 + practice_h + 2 do
    table.insert(lines, {})
  end
  table.insert(lines, {})
  for _, line in ipairs(said) do
    table.insert(lines, line)
  end
  for _ = #said, 2 do
    table.insert(lines, {})
  end
  table.insert(lines, {})
  for i, line in ipairs(lines) do
    lines[i] = vim.list_extend({ { "  " } }, line)
  end
  paint(frame_buf, lines)

  local height = math.min(#lines, rows - 2)
  local label = (task.label or string.format("task %d/%d", current, #tasks)):lower()
  vim.api.nvim_win_set_config(frame_win, {
    relative = "editor", width = outer - 2, height = height,
    row = math.max(0, math.floor((rows - height - 2) / 2)), col = math.floor((columns - outer) / 2),
    title = { { "─", "VimniscientFrame" }, { " " .. session.title .. " ", TITLE } }, title_pos = "left",
    footer = { { " " .. label .. " ", MUTED }, { "─", "VimniscientFrame" } }, footer_pos = "right",
  })
  vim.api.nvim_win_set_config(goal_win, {
    relative = "win", win = frame_win, row = goal_row, col = 2, width = box, height = goal_h,
    title = { { "─", "VimniscientBox" }, { " goal ", MUTED } }, title_pos = "left",
  })
  local mode = MODES[vim.fn.mode():sub(1, 1)] or vim.fn.mode()
  local keys = task.budget and string.format("keys %d of %d · ref %d", count, task.budget, task.ref)
    or string.format("keys %d · ref %d", count, task.ref)
  vim.api.nvim_win_set_config(practice_win, {
    relative = "win", win = frame_win, row = goal_row + goal_h + 2, col = 2, width = box, height = practice_h,
    title = { { "─", "VimniscientFrame" }, { " you ", TITLE } }, title_pos = "left",
    footer = { { " " .. mode .. " · " .. keys .. " ", MUTED }, { "─", "VimniscientFrame" } }, footer_pos = "right",
  })

  local commands = task.solution == "—" and { { ":Reset", "start over" }, { ":q", "stop" } }
    or { { ":Hint", "a clue, twice for the answer" }, { ":Skip", "skip" }, { ":Reset", "start over" }, { ":q", "stop" } }
  local bar = { { " " } }
  for i, c in ipairs(commands) do
    vim.list_extend(bar, { { (i > 1 and "  " or "") .. c[1], TITLE }, { " " .. c[2], MUTED } })
  end
  paint(keys_buf, { bar })
  vim.api.nvim_win_set_config(keys_win, { relative = "editor", row = rows, col = 0, width = columns, height = 1 })
end

local function set_lines(buf, lines)
  vim.bo[buf].modifiable = true
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
end

local function write_results()
  local f = io.open(session.result_path, "w")
  if f then
    f:write(vim.json.encode(results))
    f:close()
  end
end

local function load_task(i)
  current = i
  local task = tasks[i]
  if not endless and i > 1 and task.phase ~= tasks[i - 1].phase and task.phase == "recall" then
    tell({ { "Recall  ", TITLE }, { "from memory now: new text, no keys shown.", MUTED } })
  end
  if endless and task.phase == "recall" then
    tell({ { "Recall  ", TITLE }, { "one you missed earlier, on new text. From memory now.", MUTED } })
  end
  state = { keys = {}, done = false, hints = 0, started = vim.uv.hrtime() }
  results[i].status = "quit"

  set_lines(goal_buf, task.target)
  vim.bo[goal_buf].modifiable = false

  -- Replace the text without leaving it on the undo stack.
  local undolevels = vim.bo[practice_buf].undolevels
  vim.bo[practice_buf].undolevels = -1
  set_lines(practice_buf, task.start)
  vim.bo[practice_buf].undolevels = undolevels

  vim.bo[practice_buf].filetype = task.ft
  vim.bo[goal_buf].filetype = task.ft
  -- Same indent settings as the validator, and no plugins typing for you.
  for _, buf in ipairs({ practice_buf, goal_buf }) do
    vim.bo[buf].shiftwidth = 4
    vim.bo[buf].tabstop = 4
    vim.bo[buf].expandtab = true
  end
  vim.b[practice_buf].minipairs_disable = true
  vim.b[practice_buf].completion = false
  vim.b[practice_buf].autoformat = false
  vim.bo[practice_buf].modified = false

  vim.fn.setreg("/", "")
  vim.cmd("nohlsearch")

  for _, win in ipairs({ goal_win, practice_win }) do
    vim.api.nvim_win_call(win, function() vim.cmd("diffthis") end)
    vim.wo[win].foldenable = false
    vim.wo[win].foldcolumn = "1"
  end
  vim.cmd("diffupdate")

  state.fresh = true
  redraw()
  vim.api.nvim_set_current_win(practice_win)
  vim.api.nvim_win_set_cursor(practice_win, task.cursor)
  -- Every task starts in normal mode (LazyVim's visual > keeps the selection).
  vim.cmd("stopinsert")
  if vim.fn.mode():find("^[vVsS\22\19]") then
    vim.api.nvim_feedkeys(vim.keycode("<Esc>"), "nx", false)
  end
  redraw()
end

local function finish(status)
  local r = results[current]
  r.status = status
  r.keys, r.count = task_keys()
  if status == "quit" then
    -- the :q that ended the lesson isn't part of the attempt
    for _, ending in ipairs({ ":qa!<CR>", ":qa<CR>", ":q!<CR>", ":q<CR>", ":wq<CR>", ":x<CR>", "ZZ", "ZQ", " qq" }) do
      if r.keys:sub(-#ending) == ending then
        r.keys = r.keys:sub(1, -#ending - 1)
        break
      end
    end
    r.count = 0
  end
  r.hints = state.hints
  -- seconds from the task appearing to it ending (:Reset doesn't restart the
  -- clock), and before the first key: time spent working out what to do
  local now = vim.uv.hrtime()
  r.seconds = (now - state.started) / 1e9
  r.first = state.first and (state.first - state.started) / 1e9
  state.done = true
  if endless then
    write_results() -- an endless run has no last task, so keep the file current
  end
end

local function next_task(delay)
  vim.defer_fn(function()
    if endless and current == #tasks then
      add_task(endless_next())
    end
    if current < #tasks then
      load_task(current + 1)
    else
      write_results()
      vim.cmd("qa!")
    end
  end, delay)
end

-- Endless: a miss shows the answer, gives the task again with the keys shown,
-- and brings it back on its next text a few tasks later.
-- Lessons: a skipped Recall task, typed with the answer shown, then once more from memory.
local function retry()
  local task = tasks[current]
  finish("skipped")
  tell(vim.list_extend({ { "✗  ", WRONG }, { task.solution, STRONG },
    { "\n" }, { "Type it in now; it comes back on new text at the end.", MUTED } }, why(task, ACCENT)))
  local learn = vim.tbl_extend("force", task, { phase = "learn", extra = "learn", show = task.solution,
    label = "LEARN · skipped" })
  local again = vim.tbl_extend("force", task.again, { phase = "recall", extra = "recall", n = task.n,
    label = "RECALL · again" })
  learn.again, again.again = nil, nil
  for _, item in ipairs({ { current + 1, learn }, { #tasks + 2, again } }) do
    table.insert(tasks, item[1], item[2])
    table.insert(results, item[1], { status = "unseen", keys = "", count = 0, hints = 0, n = task.n, extra = item[2].extra })
  end
  next_task(0)
end

local function miss(reason)
  local task = tasks[current]
  finish("failed")
  tell(vim.list_extend({ { "✗  ", WRONG }, { task.solution, STRONG }, { "   " .. reason, MUTED },
    { "\n" }, { "Type it in now; it comes back on new text soon.", MUTED } }, why(task, ACCENT)))
  add_task(endless_task(task.id, task.v, "learn"))
  table.insert(climb.pending, { id = task.id, v = task.v + 1, after = climb.rung + endless.gap })
  next_task(0)
end

local function over_budget()
  local task = tasks[current]
  if state.done or not (task and task.budget) or vim.fn.mode() == "c" then
    return -- an Ex command counts once it's entered
  end
  local _, count = task_keys()
  if count > task.budget then
    miss(string.format("Over the budget of %d keys.", task.budget))
  end
end

local function check()
  if state.done or current == 0 then
    return
  end
  local mode = vim.fn.mode()
  if mode:find("^i") or mode:find("^R") then
    return
  end
  local lines = vim.api.nvim_buf_get_lines(practice_buf, 0, -1, false)
  if vim.deep_equal(lines, tasks[current].target) then
    local task = tasks[current]
    if task.budget and select(2, task_keys()) > task.budget then
      miss(string.format("Solved, but over the budget of %d keys.", task.budget))
      return
    end
    finish("solved")
    local r = results[current]
    local ref = tasks[current].ref
    local verdict = r.count < ref and " · beat the ref!" or r.count == ref and " · matched the ref" or ""
    local said = { { "✓  ", RIGHT }, { r.keys, STRONG },
      { string.format("   %d %s · ref %d%s", r.count, r.count == 1 and "key" or "keys", ref, verdict), MUTED } }
    if r.keys ~= task.solution and task.solution ~= "—" then
      vim.list_extend(said, { { "\n" }, { "ref  ", MUTED }, { task.solution, STRONG } })
    end
    if endless then
      local phase = task.phase
      if phase == "climb" then
        climb.level = climb.level + 1
      end
      local next = phase == "climb" and string.format("Level %d", climb.level)
        or phase == "recall" and "Recalled" or "Learnt: it comes back soon on new text"
      vim.list_extend(said, { { "\n" }, { next, TITLE } })
    elseif current == #tasks then
      vim.list_extend(said, { { "\n" }, { "Lesson done.", TITLE } })
    end
    tell(vim.list_extend(said, why(task, MUTED)))
    next_task(1400)
  end
end

local ns = vim.api.nvim_create_namespace("vimniscient")
-- `typed` is empty for keys a plugin fed in, and holds a whole mapping at
-- once when one completes (`iw` after `c`).
vim.on_key(function(_, typed)
  if not state.done and typed and typed ~= "" then
    -- a plain space, as the reference solutions write it
    state.first = state.first or vim.uv.hrtime()
    table.insert(state.keys, (vim.fn.keytrans(typed):gsub("<Space>", " ")))
    if state.fresh then -- what was said about the last task has been read
      state.fresh = false
      feedback = {}
    end
    vim.schedule(redraw)
    if endless then
      vim.schedule(over_budget)
    end
  end
end, ns)

local group = vim.api.nvim_create_augroup("vimniscient", { clear = true })
vim.api.nvim_create_autocmd({ "TextChanged", "InsertLeave" }, {
  group = group,
  buffer = practice_buf,
  callback = function() vim.schedule(check) end,
})
-- The boxes grow with the text, and the footer shows the mode.
vim.api.nvim_create_autocmd({ "TextChangedI", "ModeChanged", "VimResized" }, {
  group = group,
  callback = function() vim.schedule(redraw) end,
})
if endless then
  vim.api.nvim_create_autocmd("CmdlineLeave", {
    group = group,
    callback = function() vim.schedule(over_budget) end,
  })
end
-- Closing either window ends the lesson.
vim.api.nvim_create_autocmd("WinClosed", {
  group = group,
  pattern = { tostring(goal_win), tostring(practice_win) },
  callback = function() vim.schedule(function() vim.cmd("qa!") end) end,
})
vim.api.nvim_create_autocmd("VimLeavePre", {
  group = group,
  callback = function()
    if not state.done and current > 0 then
      finish("quit")
    end
    write_results()
  end,
})

vim.api.nvim_create_user_command("Hint", function()
  local task = tasks[current]
  state.hints = state.hints + 1
  if task.solution == "—" -- VimGolf: there's no reference to give away
    or state.hints == 1 and task.hint ~= "" then
    tell({ { "hint  ", ACCENT }, { task.hint } })
  elseif endless and task.budget and not state.done then
    miss("You asked for the answer.")
  else
    tell(vim.list_extend({ { "answer  ", ACCENT }, { task.solution, STRONG } }, why(task, MUTED)))
  end
end, {})
vim.api.nvim_create_user_command("Skip", function()
  if state.done then
    return
  end
  if endless and tasks[current].budget then
    miss("Skipped.")
    return
  end
  if session.retry and tasks[current].again and tasks[current].phase == "recall" then
    retry()
    return
  end
  finish("skipped")
  next_task(0)
end, {})
vim.api.nvim_create_user_command("Reset", function()
  local undolevels = vim.bo[practice_buf].undolevels
  vim.bo[practice_buf].undolevels = -1
  set_lines(practice_buf, tasks[current].start)
  vim.bo[practice_buf].undolevels = undolevels
  vim.api.nvim_win_set_cursor(practice_win, tasks[current].cursor)
  vim.cmd("stopinsert")
  -- a fresh start: the keys count from here (hints used still count)
  state.keys = {}
  redraw()
end, {})

if endless then
  add_task(endless_next())
  load_task(1)
  tell({ { "Endless, from level " .. climb.level .. ". ", TITLE }, { "Solve within the key budget to climb; a miss "
    .. "shows the answer, and the task comes back. :q stops whenever you like.", MUTED } })
else
  load_task(1)
  tell({ { "Make your text match the goal; the next task loads by itself.", MUTED } })
end
