-- Training wheels for Vimniscient (~/Projects/code/vimniscient).
--
-- hardtime.nvim: hints first. It blocks bad habits and arrow keys once
-- Vimniscient says so: after week 2 (counts, find, search, the dot: what its
-- hints point you to) and four weeks at the earliest. The app writes the phase
-- to ~/.local/share/vimniscient/hardtime.
-- precognition.nvim: shows where motions land; toggle with <leader>uV.
-- It starts hidden: while its hints are showing, keys typed fast after an
-- operator get lost (`cia` + text, or `ciw` right after startup).

local function hardtime_phase()
  local data = os.getenv("XDG_DATA_HOME") or vim.fn.expand("~/.local/share")
  local f = io.open(data .. "/vimniscient/hardtime", "r")
  if not f then
    return "hint"
  end
  local phase = vim.trim(f:read("*a") or "")
  f:close()
  return phase == "block" and "block" or "hint"
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
