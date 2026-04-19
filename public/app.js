const canvas = document.getElementById("canvas");
const newNoteBtn = document.getElementById("new-note-btn");
const noteTemplate = document.getElementById("note-template");
const bigClock = document.getElementById("big-clock");
const generationCountdown = document.getElementById("generation-countdown");
const lastSummary = document.getElementById("last-summary");

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
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function updateBigClock() {
  bigClock.textContent = formatClock(new Date());
}

function updateGenerationCountdown() {
  if (typeof nextRunEpochMs !== "number") {
    generationCountdown.textContent = "15:00";
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

    // Detect cycle rollover: server cleared the board — reload notes.
    if (status.cycle_id && status.cycle_id !== currentCycleId) {
      if (currentCycleId !== null) {
        // A new cycle started while the user was on the page — flush stale notes.
        canvas.innerHTML = "";
        await loadNotes();
        showToast("✨ New cycle — the board has been reset!");
      }
      currentCycleId = status.cycle_id;
    }
  } catch (_error) {
    lastSummary.textContent = "Could not fetch the current generation status.";
  }
}

async function createNewNote() {
  const text = window.prompt("What's your tiny whimsical idea?", "");
  if (text === null || text.trim() === "") return;

  try {
    const note = await requestJson("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.trim(),
        x: 30 + Math.floor(Math.random() * 260),
        y: 20 + Math.floor(Math.random() * 200),
        color: pickRandomColor(),
      }),
    });
    const noteEl = createNoteElement(note);
    noteEl.classList.add("just-added");
    canvas.appendChild(noteEl);
    // scroll the new note into view + remove the highlight after the animation
    noteEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setTimeout(() => noteEl.classList.remove("just-added"), 1200);
    showToast(note.author_label ? `Posted as ${note.author_label}` : "Post-it added");
  } catch (_error) {
    alert("Could not create a new post-it.");
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

// Seed cycle_id before first status poll so a cycle already in progress
// doesn't trigger a spurious board flush.
requestJson("/api/cycle/current").then((c) => { currentCycleId = c.cycle_id || null; }).catch(() => {});
loadNotes();
updateBigClock();
updateGenerationCountdown();
refreshWorkerStatus();

setInterval(updateBigClock, 1000);
setInterval(updateGenerationCountdown, 1000);
setInterval(refreshWorkerStatus, 15000);
