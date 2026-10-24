-- Runs one Vimniscient lesson inside the user's own Neovim.
--
-- Started as `nvim -i NONE practice.txt -S runner.lua` with
-- $VIMNISCIENT_SESSION pointing at a JSON file:
--   { title, result_path, tasks = { { goal, start, cursor, target, ref, hint, solution, ft } } }
-- The goal is shown in a read-only split above, diffed against the practice
-- buffer. A task is solved as soon as the buffer matches the target in normal
-- mode; results go to result_path when Neovim exits.
--
-- Keystrokes are the `typed` part of vim.on_key, i.e. what was pressed before
-- any mapping applied (as VimGolf counts them).

local session = vim.json.decode(io.open(os.getenv("VIMNISCIENT_SESSION")):read("*a"))
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

local results = {}
for i = 1, #tasks do
  results[i] = { status = "unseen", keys = "", count = 0, hints = 0 }
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
    "%%#Title# GOAL %d/%d %%* %s",
    current, #tasks, esc(task.goal)
  )
  vim.wo[practice_win].winbar = string.format(
    "%%#Title# YOU %%* keys %d · ref %d %%=:Hint  :Skip  :Reset  :q quit ",
    count, task.ref
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
    for _, ending in ipairs({ ":qa!<CR>", ":qa<CR>", ":q!<CR>", ":q<CR>", ":wq<CR>", ":x<CR>", "ZZ", "ZQ" }) do
      if r.keys:sub(-#ending) == ending then
        r.keys = r.keys:sub(1, -#ending - 1)
        break
      end
    end
    r.count = 0
  end
  r.hints = state.hints
  state.done = true
end

local function next_task(delay)
  vim.defer_fn(function()
    if current < #tasks then
      load_task(current + 1)
    else
      write_results()
      vim.cmd("qa!")
    end
  end, delay)
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
    finish("solved")
    local r = results[current]
    local ref = tasks[current].ref
    local verdict = r.count < ref and "  beat the ref!" or r.count == ref and "  matched the ref" or ""
    local last = current == #tasks and "\nLesson done." or ""
    vim.notify(string.format("Solved in %d keys (ref %d)%s\n%s%s", r.count, ref, verdict, r.keys, last),
      vim.log.levels.INFO, { title = "Vimniscient" })
    next_task(1400)
  end
end

local ns = vim.api.nvim_create_namespace("vimniscient")
-- `typed` is empty for keys a plugin fed in, and holds a whole mapping at
-- once when one completes (`iw` after `c`).
vim.on_key(function(_, typed)
  if not state.done and typed and typed ~= "" then
    table.insert(state.keys, vim.fn.keytrans(typed))
    vim.schedule(update_winbars)
  end
end, ns)

local group = vim.api.nvim_create_augroup("vimniscient", { clear = true })
vim.api.nvim_create_autocmd({ "TextChanged", "InsertLeave" }, {
  group = group,
  buffer = practice_buf,
  callback = function() vim.schedule(check) end,
})
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
  if state.hints == 1 and task.hint ~= "" then
    vim.notify(task.hint, vim.log.levels.INFO, { title = "Hint" })
  else
    vim.notify("Reference solution: " .. task.solution, vim.log.levels.INFO, { title = "Hint" })
  end
end, {})
vim.api.nvim_create_user_command("Skip", function()
  if state.done then
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
end, {})

load_task(1)
vim.notify(session.title .. "\nMake the bottom text match the goal.", vim.log.levels.INFO, { title = "Vimniscient" })
