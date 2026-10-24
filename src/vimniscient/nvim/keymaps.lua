-- nvim --headless -i NONE -n -S keymaps.lua, with $VIMNISCIENT_KEYMAPS = output path.
-- Loads the whole user config (LazyVim loads its keymaps on VeryLazy, which
-- never fires headless) and writes every keymap that has a description.

local lazy_ok, lazy = pcall(require, "lazy")
if lazy_ok then
  lazy.load({ plugins = vim.tbl_map(function(p) return p.name end, lazy.plugins()), wait = true })
end
vim.api.nvim_exec_autocmds("User", { pattern = "VeryLazy" })

vim.defer_fn(function()
  local out = {}
  for _, mode in ipairs({ "n", "x", "i" }) do
    for _, m in ipairs(vim.api.nvim_get_keymap(mode)) do
      if m.desc and m.desc ~= "" then
        -- lhs comes back printable except for spaces (the leader)
        table.insert(out, { mode = mode, lhs = (m.lhs:gsub(" ", "<Space>")), desc = m.desc })
      end
    end
  end
  local f = io.open(os.getenv("VIMNISCIENT_KEYMAPS"), "w")
  f:write(vim.json.encode(out))
  f:close()
  vim.cmd("qa!")
end, 300)
