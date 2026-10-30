CREATE TABLE attempts (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    lesson TEXT NOT NULL,
    task INTEGER NOT NULL,
    status TEXT NOT NULL,
    count INTEGER NOT NULL,
    ref INTEGER NOT NULL,
    keys TEXT NOT NULL,
    hints INTEGER NOT NULL
, phase TEXT NOT NULL DEFAULT 'recall', seconds REAL, first REAL);
CREATE TABLE card_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    card TEXT NOT NULL,
    correct INTEGER NOT NULL,
    answer TEXT NOT NULL
, intro INTEGER NOT NULL DEFAULT 0);
CREATE TABLE drill_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    drill TEXT NOT NULL,
    seconds REAL NOT NULL,
    hinted INTEGER NOT NULL,
    skipped INTEGER NOT NULL
);
CREATE TABLE endless_runs (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    start INTEGER NOT NULL,
    level INTEGER NOT NULL,
    climbed INTEGER NOT NULL,
    missed INTEGER NOT NULL,
    fixed INTEGER NOT NULL
);
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    ease REAL NOT NULL,
    interval REAL NOT NULL,
    due TEXT NOT NULL,
    reps INTEGER NOT NULL,
    lapses INTEGER NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE placed (
    lesson TEXT PRIMARY KEY,
    ts TEXT NOT NULL
);
CREATE TABLE vimgolf (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    assigned TEXT NOT NULL,
    best INTEGER,
    score INTEGER,
    solved TEXT
);
