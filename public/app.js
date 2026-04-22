const canvas = document.getElementById("canvas");
const newNoteBtn = document.getElementById("new-note-btn");
const noteTemplate = document.getElementById("note-template");
const bigClock = document.getElementById("big-clock");
const generationCountdown = document.getElementById("generation-countdown");
const lastSummary = document.getElementById("last-summary");
const historyList = document.getElementById("history-list");

const NOTE_PALETTE = [
  "rgba(250, 248, 243, 0.95)", // cream
  "rgba(253, 232, 219, 0.95)", // peach light
  "rgba(244, 194, 167, 0.95)", // peach
  "rgba(200, 184, 219, 0.95)", // lavender
  "rgba(212, 255, 212, 0.95)", // mint
  "rgba(255, 245, 220, 0.95)", // warm cream
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
  noteEl.style.background = note.color || pickRandomColor();
  textarea.value = note.text || "";
  if (authorEl) authorEl.textContent = note.author_label ? `${note.author_label}` : "";

  if (note.is_owner) {
    // Show delete button only to the creator
    deleteBtn.style.display = "flex";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("Remove this note from the garden?")) return;
      try {
        const resp = await fetch(`/api/notes/${note.id}`, { method: "DELETE" });
        if (!resp.ok) throw new Error(`${resp.status}`);
        noteEl.remove();
        showToast("Note removed from garden");
        if (window.gardenAudio) window.gardenAudio.noteDeleted();
      } catch (_err) {
        showToast("Could not remove that note.");
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
      li.textContent = "No growth records yet";
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
    historyList.innerHTML = `<li class="history-empty">Could not load growth history</li>`;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>\\"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

async function loadNotes() {
  try {
    const notes = await requestJson("/api/notes");
    notes.forEach((note) => canvas.appendChild(createNoteElement(note)));
  } catch (_error) {
    alert("Could not load notes from the garden.");
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
  if (!bigClock) return;
  bigClock.textContent = formatClock(new Date());
}

function updateGenerationCountdown() {
  if (!generationCountdown) return;
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
    if (lastSummary) {
      lastSummary.textContent = status.summary || "Waiting for the garden keeper's notes...";
    }
    updateGenerationCountdown();

    // Detect cycle rollover: server cleared the board — reload notes + history.
    if (status.cycle_id && status.cycle_id !== currentCycleId) {
      if (currentCycleId !== null) {
        // A new cycle started while the user was on the page — flush stale notes.
        canvas.innerHTML = "";
        await loadNotes();
        loadHistory();
        showToast("🌸 New bloom cycle — the garden has been refreshed!");
      }
      currentCycleId = status.cycle_id;
    }
  } catch (_error) {
    if (lastSummary) {
      lastSummary.textContent = "Could not fetch the current garden status.";
    }
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
  const text = window.prompt("Plant your idea in the garden:", "");
  if (text === null || text.trim() === "") return;

  // Disable button and show working state while PoW runs
  newNoteBtn.disabled = true;
  const origLabel = newNoteBtn.innerHTML;
  newNoteBtn.innerHTML = '<svg class="button-icon" viewBox="0 0 24 24" width="20" height="20"><circle cx="12" cy="12" r="10"/></svg> Growing...';
  try {
    // 1. Get the current PoW challenge from the server
    const pow = await requestJson("/api/pow-challenge");

    // 2. Solve it in a background Web Worker (non-blocking)
    showToast("🌱 Preparing your seed...");
    const nonce = await solvePow(pow.challenge, pow.difficulty_submit);

    // 3. POST the note
    const note = await requestJson("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.trim(),
        pow: nonce,
        challenge: pow.challenge,
        x: 30 + Math.floor(Math.random() * 300),
        y: 50 + Math.floor(Math.random() * 250),
        color: pickRandomColor(),
      }),
    });

    const noteEl = createNoteElement(note);
    noteEl.classList.add("just-added");
    canvas.appendChild(noteEl);
    noteEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setTimeout(() => noteEl.classList.remove("just-added"), 1200);
    
    const message = note.author_label ? `🌸 Planted as ${note.author_label}` : "🌸 Idea planted!";
    showToast(message);
    
    if (window.gardenAudio) window.gardenAudio.noteCreated();
  } catch (_error) {
    alert("Could not plant your idea. Please try again.");
  } finally {
    newNoteBtn.disabled = false;
    newNoteBtn.innerHTML = origLabel;
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
  const x = Math.max(0, Math.round(event.clientX - rect.left - 110));
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
    alert("Could not move that note right now.");
  }
});

newNoteBtn.addEventListener("click", createNewNote);

// The manual cycle trigger is operator-only now; it lives on /logs?token=…
// No public UI element for it.

// Seed cycle_id before first status poll so a cycle already in progress
// doesn't trigger a spurious board flush.
requestJson("/api/cycle/current").then((c) => { currentCycleId = c.cycle_id || null; }).catch(() => {});

/**
 * Populate the "previous cycle" preview section. Fetches the most recent cycle
 * metadata from /api/cycles/previous and renders it into the mandated DOM
 * anchors: #prev-cycle-summary, #prev-cycle-count, #prev-cycle-notes-list.
 * The chaos agent is required to keep these IDs; without them this function
 * silently no-ops.
 */
async function loadPreviousCycle() {
  const section = document.getElementById("previous-cycle");
  const summaryEl = document.getElementById("prev-cycle-summary");
  const countEl = document.getElementById("prev-cycle-count");
  const listEl = document.getElementById("prev-cycle-notes-list");
  if (!section || !summaryEl || !listEl) return;
  try {
    const res = await fetch("/api/cycles/previous");
    if (!res.ok) return;
    const data = await res.json();
    if (!data || !data.handoff_id) {
      // no previous cycle yet — keep hidden
      return;
    }
    const notes = Array.isArray(data.notes) ? data.notes : [];
    const parts = [];
    if (data.summary) parts.push(data.summary);
    if (data.agent_summary) parts.push("→ " + data.agent_summary);
    summaryEl.textContent = parts.join(" ");
    if (countEl) countEl.textContent = String(notes.length);
    listEl.innerHTML = "";
    notes.forEach((n) => {
      const li = document.createElement("li");
      const v = document.createElement("span");
      v.className = "votes";
      v.textContent = `${n.votes || 0}`;
      const t = document.createElement("span");
      t.textContent = " " + (n.text || "");
      li.appendChild(v);
      li.appendChild(t);
      listEl.appendChild(li);
    });
    section.hidden = false;
  } catch (_err) {
    /* silent */
  }
}

loadNotes();
loadHistory();
loadPreviousCycle();
updateBigClock();
updateGenerationCountdown();
refreshWorkerStatus();

setInterval(updateBigClock, 1000);
setInterval(updateGenerationCountdown, 1000);
setInterval(refreshWorkerStatus, 15000);
