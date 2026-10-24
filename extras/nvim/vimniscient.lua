-- Training wheels for Vimniscient (~/Projects/code/vimniscient).
--
-- hardtime.nvim: hints only for the first 14 days after the first
-- `vimniscient` run, then it blocks bad habits and arrow keys.
-- precognition.nvim: shows where motions land; toggle with <leader>uV.
-- It starts hidden: while its hints are showing, keys typed fast after an
-- operator get lost (`cia` + text, or `ciw` right after startup).

local function hardtime_phase()
  local f = io.open(vim.fn.expand("~/.local/share/vimniscient/started"), "r")
  if not f then
    return "hint"
  end
  local y, m, d = f:read("*l"):match("(%d+)-(%d+)-(%d+)")
  f:close()
  if not y then
    return "hint"
  end
  local started = os.time({ year = tonumber(y), month = tonumber(m), day = tonumber(d), hour = 0 })
  return os.difftime(os.time(), started) > 14 * 86400 and "block" or "hint"
end

return {
  {
    "m4xshen/hardtime.nvim",
    event = "VeryLazy",
    dependencies = { "MunifTanjim/nui.nvim" },
    opts = function()
      local block = hardtime_phase() == "block"
      return {
        restriction_mode = block and "block" or "hint",
        disable_mouse = false,
        -- arrow keys stay usable during the hint phase
        disabled_keys = block and nil or {},
      }
    end,
  },
  {
    "tris203/precognition.nvim",
    event = "VeryLazy",
    -- targetedMotionHints mangles fast operator input even more, so it stays off.
    opts = { startVisible = false, targetedMotionHints = { enabled = false } },
    keys = {
      { "<leader>uV", function() require("precognition").toggle() end, desc = "Toggle Motion Hints" },
    },
  },
}
