"""Feed made-up Hyprland events to every drill and check the steps tick off,
and that look-alike events (another window, another workspace) don't count.

    uv run python tests/check_drills.py
"""

import sys

from vimniscient.drills import DrillRun, load_drills

DRILL, OTHER, NEW, HOME = "aaa111", "bbb222", "ccc333", "2"

GOOD = {
    "focus": [f"activewindowv2>>{DRILL}", f"activewindowv2>>{OTHER}", f"activewindowv2>>{DRILL}"],
    "float": [f"changefloatingmode>>{OTHER},1", f"changefloatingmode>>{DRILL},1", f"changefloatingmode>>{DRILL},0"],
    "fullscreen": [f"activewindowv2>>{OTHER}", "fullscreen>>1", "fullscreen>>0",
                   f"activewindowv2>>{DRILL}", "fullscreen>>1", "fullscreen>>0"],
    "full-width": [f"activewindowv2>>{DRILL}", "fullscreen>>1", "fullscreen>>0"],
    "pop": [f"pin>>{DRILL},1", f"pin>>{DRILL},0"],
    "workspace-visit": ["workspacev2>>3,3", "workspacev2>>9,9", "workspacev2>>2,2"],
    "workspace-move": [f"movewindowv2>>{OTHER},9,9", f"movewindowv2>>{DRILL},9,9", "workspacev2>>9,9",
                       f"movewindowv2>>{DRILL},2,2"],
    "terminal": [f"openwindow>>{NEW},2,foot,dima@host:~", f"closewindow>>{OTHER}", f"closewindow>>{NEW}"],
    "close": [f"closewindow>>{OTHER}", f"closewindow>>{DRILL}"],
}
# Each of these must leave the drill unfinished.
BAD = {
    "focus": [f"activewindowv2>>{DRILL}", f"activewindowv2>>{DRILL}"],
    "float": [f"changefloatingmode>>{OTHER},1", f"changefloatingmode>>{OTHER},0"],
    "fullscreen": [f"activewindowv2>>{OTHER}", "fullscreen>>1", "fullscreen>>0"],
    "workspace-visit": ["workspacev2>>9,9", "workspacev2>>4,4"],
    "terminal": [f"openwindow>>{NEW},2,foot,x", f"closewindow>>{OTHER}"],
}

failed = 0
drills = {d.id: d for d in load_drills()}
for drill_id, drill in drills.items():
    if drill_id not in GOOD:
        failed += 1
        print(f"FAIL {drill_id}: no test events")
        continue
    run = DrillRun(drill, DRILL, HOME)
    for line in GOOD[drill_id]:
        run.feed(line)
    if not run.finished:
        failed += 1
        print(f"FAIL {drill_id}: stuck at step {run.step + 1}")
for drill_id, lines in BAD.items():
    run = DrillRun(drills[drill_id], DRILL, HOME)
    for line in lines:
        run.feed(line)
    if run.finished:
        failed += 1
        print(f"FAIL {drill_id}: finished on events that shouldn't count")
print(f"{len(drills)} drills, {failed} failed")
sys.exit(1 if failed else 0)
