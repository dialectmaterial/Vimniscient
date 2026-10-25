// Plays a lesson back the way the runner shows it: Learn with the keys shown,
// then Recall on another text, from memory. Only ciw and daw are simulated.
(() => {
  const tasks = [
    { label: "LEARN 1/6", goal: 'Fix "while" to "whole".', start: "ciw is change inner word: it swaps the while word, wherever the cursor sits.",
      cursor: 41, target: "ciw is change inner word: it swaps the whole word, wherever the cursor sits.", keys: "ciwwhole<Esc>", ref: 9, show: true },
    { label: "LEARN 2/6", goal: 'Delete one "own", including its space.', start: "The a in daw is around: the word and its own own space.",
      cursor: 45, target: "The a in daw is around: the word and its own space.", keys: "daw", ref: 3, show: true },
    { label: "RECALL 1/6", goal: 'Fix "spaec" to "space".', start: "The i in ciw means inner: just the word, never the spaec around it.",
      cursor: 54, target: "The i in ciw means inner: just the word, never the space around it.", keys: "ciwspace<Esc>", ref: 9, show: false,
      notice: "From memory now: new text, no keys shown." },
  ];

  const $ = (id) => document.getElementById(id);
  const el = { label: $("d-label"), goal: $("d-goal"), target: $("d-target"), text: $("d-text"), count: $("d-count"),
    ref: $("d-ref"), show: $("d-show"), typed: $("d-typed"), notify: $("d-notify"), mode: $("d-mode") };
  if (!el.text) return;

  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const tokens = (keys) => keys.match(/<[^<>]+>|./g);
  const isWord = (c) => /\w/.test(c || "");

  // Where the two lines differ: [start, end in a, end in b].
  function diff(a, b) {
    let i = 0;
    while (i < a.length && i < b.length && a[i] === b[i]) i++;
    let ea = a.length, eb = b.length;
    while (ea > i && eb > i && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
    return [i, ea, eb];
  }

  // A line with its changed part highlighted and, optionally, the cursor.
  function render(line, from, to, cursor, insert) {
    let html = "";
    for (let i = 0; i <= line.length; i++) {
      if (i === from && to > from) html += '<span class="chg">';
      if (i === to && to > from) html += "</span>";
      if (i === line.length) {
        if (cursor === i) html += `<span class="cur${insert ? " bar" : ""}"> </span>`;
        break;
      }
      const c = esc(line[i]);
      html += cursor === i ? `<span class="cur${insert ? " bar" : ""}">${c}</span>` : c;
    }
    return html;
  }

  function show(state, task) {
    const [i, ea, eb] = diff(task.target, state.text);
    el.target.innerHTML = render(task.target, i, ea, -1, false);
    el.text.innerHTML = render(state.text, i, eb, state.cursor, state.insert);
    el.mode.textContent = state.insert ? "INSERT" : "NORMAL";
    el.mode.classList.toggle("insert", state.insert);
  }

  // Apply one key to the buffer: ciw/daw on the word under the cursor, then text in insert mode.
  function press(state, key) {
    const t = state.text;
    if (state.insert) {
      if (key === "<Esc>") { state.insert = false; state.cursor = Math.max(0, state.cursor - 1); return; }
      state.text = t.slice(0, state.cursor) + key + t.slice(state.cursor);
      state.cursor++;
      return;
    }
    state.pending += key;
    if (state.pending === "ciw" || state.pending === "daw") {
      let s = state.cursor, e = state.cursor;
      while (s > 0 && isWord(t[s - 1])) s--;
      while (e < t.length && isWord(t[e])) e++;
      if (state.pending === "daw") while (t[e] === " ") e++;
      state.text = t.slice(0, s) + t.slice(e);
      state.cursor = s;
      state.insert = state.pending === "ciw";
      state.pending = "";
    }
  }

  function notify(title, body, kind) {
    el.notify.className = "notify" + (kind ? " " + kind : "");
    el.notify.innerHTML = `<span class="t">${esc(title)}</span>${body}`;
    el.notify.hidden = false;
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function load(task) {
    el.label.textContent = task.label;
    el.goal.textContent = task.goal;
    el.ref.textContent = task.ref;
    el.count.textContent = "0";
    el.show.innerHTML = task.show ? ` <span class="show">type <b>${esc(task.keys)}</b></span>` : "";
    el.typed.textContent = "";
    const state = { text: task.start, cursor: task.cursor, insert: false, pending: "" };
    show(state, task);
    return state;
  }

  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (still) {
    // No playback: the first task, solved.
    const task = tasks[0], state = load(task);
    tokens(task.keys).forEach((k) => press(state, k));
    show(state, task);
    el.count.textContent = task.ref;
    el.typed.textContent = task.keys;
    notify("Vimniscient", `Solved in ${task.ref} keys (ref ${task.ref}), matched the ref`);
    return;
  }

  async function play() {
    for (;;) {
      for (const task of tasks) {
        el.notify.hidden = true;
        const state = load(task);
        if (task.notice) { notify("Recall", esc(task.notice), "recall"); await sleep(1900); el.notify.hidden = true; }
        await sleep(900);
        let n = 0;
        for (const key of tokens(task.keys)) {
          press(state, key);
          n++;
          el.count.textContent = n;
          el.typed.textContent += key;
          show(state, task);
          await sleep(key === "<Esc>" ? 380 : state.insert ? 95 : 260);
        }
        const verdict = n < task.ref ? ", beat the ref!" : n === task.ref ? ", matched the ref" : "";
        notify("Vimniscient", `Solved in ${n} keys (ref ${task.ref})${verdict}<br><span class="dim">${esc(task.keys)}</span>`);
        await sleep(2200);
      }
    }
  }

  // Start when it scrolls into view.
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { io.disconnect(); play(); }
  }, { threshold: 0.3 });
  load(tasks[0]);
  io.observe($("demo"));
})();

// Copy buttons
document.querySelectorAll(".copy").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.textContent = "copied";
      button.classList.add("done");
      setTimeout(() => { button.textContent = "copy"; button.classList.remove("done"); }, 1600);
    } catch {
      button.textContent = "select it";
    }
  });
});
