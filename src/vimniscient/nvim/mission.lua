-- A multi-file mission, in your own Neovim. `nvim -S mission.lua`, with
-- VIMNISCIENT_MISSION naming a JSON file: { goal, hint, ref, targets = { name = lines }, result_path }.
-- Every save checks all the files; when they match, the result is written and Neovim quits.

local session = vim.json.decode(table.concat(vim.fn.readfile(vim.env.VIMNISCIENT_MISSION), "\n"))
local started = vim.uv.hrtime()
local first, count, keys, finished = nil, 0, {}, false

vim.g.autoformat = false -- a formatter would change the files under the check

local function seconds(from)
  return (vim.uv.hrtime() - from) / 1e9
end

local function finish(status)
  if finished then
    return
  end
  finished = true
  vim.fn.writefile({ vim.json.encode({
    status = status,
    keys = table.concat(keys),
    count = count,
    seconds = seconds(started),
    first = first,
    hints = session.hints or 0,
  }) }, session.result_path)
end

local function wrong()
  local files = {}
  for name, target in pairs(session.targets) do
    if vim.fn.filereadable(name) == 0 or not vim.deep_equal(vim.fn.readfile(name), target) then
      table.insert(files, name)
    end
  end
  table.sort(files)
  return files
end

local buf = vim.api.nvim_create_buf(false, true)
local function card(lines)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
end
local width = math.min(64, vim.o.columns - 4)
card({ session.goal, ":Check what's left  :Hint a clue  :Skip give up" })
vim.api.nvim_open_win(buf, false, {
  relative = "editor", row = 1, col = vim.o.columns - width - 2, width = width, height = 3,
  style = "minimal", border = "rounded", title = " mission ", focusable = false, zindex = 60,
})
vim.api.nvim_set_option_value("wrap", true, { win = vim.fn.bufwinid(buf) })

vim.on_key(function(_, typed)
  if typed and typed ~= "" and not finished then
    first = first or seconds(started)
    count = count + 1
    table.insert(keys, vim.fn.keytrans(typed))
  end
end)

vim.api.nvim_create_autocmd("BufWritePost", {
  callback = function()
    vim.schedule(function()
      if #wrong() == 0 then
        finish("solved")
        vim.cmd("qa!")
      end
    end)
  end,
})
vim.api.nvim_create_autocmd("VimLeavePre", { callback = function() finish("quit") end })

vim.api.nvim_create_user_command("Check", function()
  local left = wrong()
  card({ session.goal, #left == 0 and "All done." or "Not yet: " .. table.concat(left, ", ") })
end, {})
vim.api.nvim_create_user_command("Hint", function()
  session.hints = (session.hints or 0) + 1
  card({ session.goal, session.hint })
end, {})
vim.api.nvim_create_user_command("Skip", function()
  finish("skipped")
  vim.cmd("qa!")
end, {})
