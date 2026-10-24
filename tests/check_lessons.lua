-- nvim --clean --headless -l tests/check_lessons.lua tasks.json
-- Plays every reference solution and prints the tasks whose result is not the target.

local tasks = vim.json.decode(io.open(_G.arg[1]):read("*a"))
vim.o.ignorecase = true -- match LazyVim's search settings
vim.o.smartcase = true

local failed = 0
for _, t in ipairs(tasks) do
  vim.cmd("enew!")
  vim.bo.shiftwidth = 4
  vim.bo.tabstop = 4
  vim.bo.expandtab = true
  vim.fn.setreg("/", "")
  vim.api.nvim_buf_set_lines(0, 0, -1, false, t.start)
  vim.api.nvim_win_set_cursor(0, t.cursor)
  vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes(t.solution, true, false, true), "xt", false)
  local got = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  if not vim.deep_equal(got, t.target) then
    failed = failed + 1
    io.stdout:write(string.format("FAIL %s: %s\n  solution: %s\n  want: %s\n  got:  %s\n",
      t.id, t.goal, t.solution, vim.inspect(t.target), vim.inspect(got)))
  end
end
io.stdout:write(string.format("%d tasks, %d failed\n", #tasks, failed))
os.exit(failed == 0 and 0 or 1)
