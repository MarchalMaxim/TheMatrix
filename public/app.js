const canvas = document.getElementById("canvas");
const newNoteBtn = document.getElementById("new-note-btn");
const noteTemplate = document.getElementById("note-template");
const bigClock = document.getElementById("big-clock");
const generationCountdown = document.getElementById("generation-countdown");
const lastSummary = document.getElementById("last-summary");
const historyList = document.getElementById("history-list");

const NOTE_PALETTE = [
  "#ffe98f", "#ffd1dc", "#c8f7c5", "#c5e3ff", "#ffd9b3",
  "#e0c8ff", "#fff5b3", "#b3f0e8", "#ffc8c8", "#d9f0a3",
];

function pickRandomColor() {
  return NOTE_PALETTE[Math.floor(Math.random() * NOTE_PALETTE.length)];
}

let toastTimer = null;
function showToast(message) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = message;
  // force reflow so transitions retrigger
  void el.offsetWidth;
  el.classList.add("show");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2500);
}

let dragNote = null;
let nextRunEpochMs = null;
let currentCycleId = null;

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return response.json();
}

function createNoteElement(note) {
  const fragment = noteTemplate.content.cloneNode(true);
  const noteEl = fragment.querySelector(".note");
  const textarea = fragment.querySelector("textarea");
  const authorEl = fragment.querySelector(".note-author");
  const deleteBtn = fragment.querySelector(".note-delete");

  noteEl.dataset.id = note.id;
  noteEl.style.left = `${note.x}px`;
  noteEl.style.top = `${note.y}px`;
  noteEl.style.background = note.color || "#ffe98f";
  textarea.value = note.text || "";
  if (authorEl) authorEl.textContent = note.author_label ? `— ${note.author_label}` : "";

  if (note.is_owner) {
    // Show delete button only to the creator
    deleteBtn.style.display = "block";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("Delete this post-it?")) return;
      try {
        const resp = await fetch(`/api/notes/${note.id}`, { method: "DELETE" });
        if (!resp.ok) throw new Error(`${resp.status}`);
        noteEl.remove();
        showToast("Post-it deleted");
      } catch (_err) {
        showToast("Could not delete that post-it.");
      }
    });
  } else {
    // Non-owners: read-only text; drag still works
    textarea.readOnly = true;
  }

  noteEl.addEventListener("dragstart", () => {
    dragNote = noteEl;
  });

  textarea.addEventListener("change", async () => {
    if (textarea.readOnly) return;
    try {
      await requestJson(`/api/notes/${note.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: textarea.value }),
      });
    } catch (_error) {
      alert("Could not save that note right now.");
    }
  });

  return noteEl;
}

async function loadHistory() {
  if (!historyList) return;
  try {
    const commits = await requestJson("/api/history");
    historyList.innerHTML = "";
    if (!commits.length) {
      const li = document.createElement("li");
      li.className = "history-empty";
      li.textContent = "No cycle commits yet. The site hasn't been rewritten by the agent yet.";
      historyList.appendChild(li);
      return;
    }
    for (const c of commits) {
      const li = document.createElement("li");
      const when = c.date ? new Date(c.date).toLocaleString() : "";
      const anchor = document.createElement("a");
      anchor.href = c.html_url || "#";
      anchor.target = "_blank";
      anchor.rel = "noopener";
      anchor.innerHTML =
        `<span class="history-sha">${c.sha}</span>` +
        `<span class="history-title-text">${escapeHtml(c.title)}</span>` +
        (when ? `<span class="history-date">${when}</span>` : "");
      li.appendChild(anchor);
      historyList.appendChild(li);
    }
  } catch (_err) {
    historyList.innerHTML = `<li class="history-empty">Could not load history right now.</li>`;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

async function loadNotes() {
  try {
    const notes = await requestJson("/api/notes");
    notes.forEach((note) => canvas.appendChild(createNoteElement(note)));
  } catch (_error) {
    alert("Could not load notes from the server.");
  }
}

function formatClock(date) {
  return date.toLocaleTimeString("en-GB", { hour12: false });
}

function formatCountdown(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(seconds)}`
    : `${pad(minutes)}:${pad(seconds)}`;
}

function updateBigClock() {
  bigClock.textContent = formatClock(new Date());
}

function updateGenerationCountdown() {
  if (typeof nextRunEpochMs !== "number") {
    generationCountdown.textContent = "4:00:00";
    return;
  }

  const seconds = Math.max(0, Math.ceil((nextRunEpochMs - Date.now()) / 1000));
  generationCountdown.textContent = formatCountdown(seconds);
}

async function refreshWorkerStatus() {
  try {
    const status = await requestJson("/api/worker-status");
    nextRunEpochMs = typeof status.next_run_epoch === "number" ? status.next_run_epoch * 1000 : null;
    lastSummary.textContent = status.summary || "Waiting for the first generation briefing...";
    updateGenerationCountdown();

    // Detect cycle rollover: server cleared the board — reload notes + history.
    if (status.cycle_id && status.cycle_id !== currentCycleId) {
      if (currentCycleId !== null) {
        // A new cycle started while the user was on the page — flush stale notes.
        canvas.innerHTML = "";
        await loadNotes();
        loadHistory();
        showToast("✨ New cycle — the board has been reset!");
      }
      currentCycleId = status.cycle_id;
    }
  } catch (_error) {
    lastSummary.textContent = "Could not fetch the current generation status.";
  }
}

/**
 * Solve proof-of-work off the main thread using a Web Worker.
 * Returns a Promise that resolves to the nonce string.
 */
function solvePow(challenge, difficulty) {
  return new Promise((resolve, reject) => {
    const worker = new Worker("/pow-worker.js");
    worker.onmessage = (e) => { worker.terminate(); resolve(e.data.nonce); };
    worker.onerror = (e) => { worker.terminate(); reject(new Error(e.message)); };
    worker.postMessage({ challenge, difficulty });
  });
}

async function createNewNote() {
  const text = window.prompt("What's your tiny whimsical idea?", "");
  if (text === null || text.trim() === "") return;

  // Disable button and show working state while PoW runs
  newNoteBtn.disabled = true;
  const origLabel = newNoteBtn.textContent;
  newNoteBtn.textContent = "⏳ Working…";
  try {
    // 1. Get the current PoW challenge from the server
    const pow = await requestJson("/api/pow-challenge");

    // 2. Solve it in a background Web Worker (non-blocking)
    showToast("⏳ Solving proof-of-work…");
    const nonce = await solvePow(pow.challenge, pow.difficulty_submit);

    // 3. POST the note
    const note = await requestJson("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.trim(),
        pow: nonce,
        challenge: pow.challenge,
        x: 30 + Math.floor(Math.random() * 260),
        y: 20 + Math.floor(Math.random() * 200),
        color: pickRandomColor(),
      }),
    });

    const noteEl = createNoteElement(note);
    noteEl.classList.add("just-added");
    canvas.appendChild(noteEl);
    noteEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setTimeout(() => noteEl.classList.remove("just-added"), 1200);
    showToast(note.author_label ? `Posted as ${note.author_label}` : "Post-it added");
  } catch (_error) {
    alert("Could not create a new post-it. Please try again.");
  } finally {
    newNoteBtn.disabled = false;
    newNoteBtn.textContent = origLabel;
  }
}

canvas.addEventListener("dragover", (event) => {
  event.preventDefault();
});

canvas.addEventListener("drop", async (event) => {
  event.preventDefault();
  if (!dragNote) {
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const x = Math.max(0, Math.round(event.clientX - rect.left - 95));
  const y = Math.max(0, Math.round(event.clientY - rect.top - 20));
  dragNote.style.left = `${x}px`;
  dragNote.style.top = `${y}px`;
  const noteId = dragNote.dataset.id;
  dragNote = null;

  try {
    await requestJson(`/api/notes/${noteId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x, y }),
    });
  } catch (_error) {
    alert("Could not move that post-it right now.");
  }
});

newNoteBtn.addEventListener("click", createNewNote);

// The manual cycle trigger is operator-only now; it lives on /logs?token=…
// No public UI element for it.

// Seed cycle_id before first status poll so a cycle already in progress
// doesn't trigger a spurious board flush.
requestJson("/api/cycle/current").then((c) => { currentCycleId = c.cycle_id || null; }).catch(() => {});
loadNotes();
loadHistory();
updateBigClock();
updateGenerationCountdown();
refreshWorkerStatus();

setInterval(updateBigClock, 1000);
setInterval(updateGenerationCountdown, 1000);
setInterval(refreshWorkerStatus, 15000);
