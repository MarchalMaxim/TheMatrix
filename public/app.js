const canvas = document.getElementById("canvas");
const newNoteBtn = document.getElementById("new-note-btn");
const noteTemplate = document.getElementById("note-template");
const bigClock = document.getElementById("big-clock");
const generationCountdown = document.getElementById("generation-countdown");
const lastSummary = document.getElementById("last-summary");

let dragNote = null;
let nextRunEpochMs = null;

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
  noteEl.dataset.id = note.id;
  noteEl.style.left = `${note.x}px`;
  noteEl.style.top = `${note.y}px`;
  noteEl.style.background = note.color || "#ffe98f";
  textarea.value = note.text || "";

  noteEl.addEventListener("dragstart", () => {
    dragNote = noteEl;
  });

  textarea.addEventListener("change", async () => {
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
  } catch (_error) {
    lastSummary.textContent = "Could not fetch the current generation status.";
  }
}

async function createNewNote() {
  try {
    const note = await requestJson("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "A tiny whimsical idea...",
        x: 30 + Math.floor(Math.random() * 260),
        y: 20 + Math.floor(Math.random() * 200),
        color: "#ffe98f",
      }),
    });
    canvas.appendChild(createNoteElement(note));
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

loadNotes();
updateBigClock();
updateGenerationCountdown();
refreshWorkerStatus();

setInterval(updateBigClock, 1000);
setInterval(updateGenerationCountdown, 1000);
setInterval(refreshWorkerStatus, 15000);
