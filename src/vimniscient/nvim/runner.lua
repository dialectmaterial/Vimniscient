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

local practice_win = vim.api.nvim_get_current_win()
local practice_buf = vim.api.nvim_get_current_buf()

vim.cmd("aboveleft new")
local goal_win = vim.api.nvim_get_current_win()
local goal_buf = vim.api.nvim_get_current_buf()
vim.bo[goal_buf].buftype = "nofile"
vim.bo[goal_buf].bufhidden = "wipe"
vim.bo[goal_buf].swapfile = false
vim.bo[goal_buf].buflisted = false
vim.api.nvim_set_current_win(practice_win)

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

-- Notifiers cut long lines short (snacks doesn't wrap), so wrap to their usual width.
local function wrap(text)
  local width = math.max(34, math.floor(vim.o.columns * 0.4) - 6)
  local out = {}
  for _, line in ipairs(vim.split(text, "\n")) do
    local current = ""
    for word in line:gmatch("%S+") do
      if current ~= "" and vim.fn.strdisplaywidth(current .. " " .. word) > width then
        table.insert(out, current)
        current = word
      else
        current = current == "" and word or current .. " " .. word
      end
    end
    table.insert(out, current)
  end
  return table.concat(out, "\n")
end

local function say(msg, level, title)
  vim.notify(wrap(msg), level, { title = title })
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

local function esc(s)
  return (s:gsub("%%", "%%%%"))
end

local function update_winbars()
  local task = tasks[current]
  if not task then
    return
  end
  local _, count = task_keys()
  vim.wo[goal_win].winbar = string.format(
    "%%#Title# %s %%* %s",
    esc(task.label or string.format("GOAL %d/%d", current, #tasks)), esc(task.goal)
  )
  local show = task.show and task.show ~= "" and string.format("  %%#Title#type%%* %s", esc(task.show)) or ""
  local keys = task.budget and string.format("keys %d of %d · ref %d", count, task.budget, task.ref)
    or string.format("keys %d · ref %d", count, task.ref)
  vim.wo[practice_win].winbar = string.format(
    "%%#Title# YOU %%* %s%s %%=:Hint  :Skip  :Reset  :q quit ", keys, show
  )
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
    say("From memory now: new text, no keys shown.", vim.log.levels.INFO, "Recall")
  end
  if endless and task.phase == "recall" then
    say("One you missed earlier, on new text. From memory now.", vim.log.levels.INFO, "Recall")
  end
  state = { keys = {}, done = false, hints = 0 }
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

  vim.api.nvim_win_set_height(goal_win, math.max(3, math.min(12, #task.target + 1)))
  for _, win in ipairs({ goal_win, practice_win }) do
    vim.api.nvim_win_call(win, function() vim.cmd("diffthis") end)
    vim.wo[win].foldenable = false
  end
  vim.cmd("diffupdate")

  vim.api.nvim_set_current_win(practice_win)
  vim.api.nvim_win_set_cursor(practice_win, task.cursor)
  -- Every task starts in normal mode (LazyVim's visual > keeps the selection).
  vim.cmd("stopinsert")
  if vim.fn.mode():find("^[vVsS\22\19]") then
    vim.api.nvim_feedkeys(vim.keycode("<Esc>"), "nx", false)
  end
  update_winbars()
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
  say(string.format("The answer: %s\nType it in now; it comes back on new text at the end.", task.solution),
    vim.log.levels.WARN, "Skipped")
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
  say(string.format("%s\nThe answer: %s\nType it in now; it comes back on new text soon.", reason, task.solution),
    vim.log.levels.WARN, "Missed")
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
    local verdict = r.count < ref and "  beat the ref!" or r.count == ref and "  matched the ref" or ""
    local last = current == #tasks and not endless and "\nLesson done." or ""
    local title = "Vimniscient"
    if endless then
      local phase = tasks[current].phase
      if phase == "climb" then
        climb.level = climb.level + 1
        title = string.format("Level %d", climb.level)
      else
        title = phase == "recall" and "Recalled" or "Learnt: it comes back soon on new text"
      end
    end
    say(string.format("Solved in %d keys (ref %d)%s\n%s%s", r.count, ref, verdict, r.keys, last),
      vim.log.levels.INFO, title)
    next_task(1400)
  end
end

local ns = vim.api.nvim_create_namespace("vimniscient")
-- `typed` is empty for keys a plugin fed in, and holds a whole mapping at
-- once when one completes (`iw` after `c`).
vim.on_key(function(_, typed)
  if not state.done and typed and typed ~= "" then
    -- a plain space, as the reference solutions write it
    table.insert(state.keys, (vim.fn.keytrans(typed):gsub("<Space>", " ")))
    vim.schedule(update_winbars)
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
  if task.solution == "—" then -- VimGolf: there's no reference to give away
    say(task.hint, vim.log.levels.INFO, "Hint")
  elseif state.hints == 1 and task.hint ~= "" then
    say(task.hint, vim.log.levels.INFO, "Hint")
  elseif endless and task.budget and not state.done then
    miss("You asked for the answer.")
  else
    say("Reference solution: " .. task.solution, vim.log.levels.INFO, "Hint")
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
  update_winbars()
end, {})

if endless then
  add_task(endless_next())
  load_task(1)
  say("Endless, from level " .. climb.level .. ". Solve within the key budget to climb; a miss shows "
    .. "the answer, and the task comes back.\n:q stops whenever you like.", vim.log.levels.INFO, "Vimniscient")
else
  load_task(1)
  say(session.title .. "\nMake the bottom text match the goal.", vim.log.levels.INFO, "Vimniscient")
end
