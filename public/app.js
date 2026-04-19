const canvas = document.getElementById("canvas");
const newNoteBtn = document.getElementById("new-note-btn");
const noteTemplate = document.getElementById("note-template");

let dragNote = null;

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
    await fetch(`/api/notes/${note.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: textarea.value }),
    });
  });

  return noteEl;
}

async function loadNotes() {
  const response = await fetch("/api/notes");
  const notes = await response.json();
  notes.forEach((note) => canvas.appendChild(createNoteElement(note)));
}

async function createNewNote() {
  const response = await fetch("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: "A tiny whimsical idea...",
      x: 30 + Math.floor(Math.random() * 260),
      y: 20 + Math.floor(Math.random() * 200),
      color: "#ffe98f",
    }),
  });
  const note = await response.json();
  canvas.appendChild(createNoteElement(note));
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

  await fetch(`/api/notes/${noteId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ x, y }),
  });
});

newNoteBtn.addEventListener("click", createNewNote);

loadNotes();
