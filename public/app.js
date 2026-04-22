const canvas = document.getElementById("canvas");
const newNoteBtn = document.getElementById("new-note-btn");
const noteTemplate = document.getElementById("note-template");
const bigClock = document.getElementById("big-clock");
const generationCountdown = document.getElementById("generation-countdown");
const lastSummary = document.getElementById("last-summary");
const historyList = document.getElementById("history-list");

const NOTE_COLORS = [
  "linear-gradient(135deg, #fffef0, #f5f5dc)",
  "linear-gradient(135deg, #faf5e8, #f4e8d0)",
  "linear-gradient(135deg, #f5f5dc, #e0d4b8)",
  "linear-gradient(135deg, #fffef0, #e0d4b8)",
];

function pickRandomColor() {
  return NOTE_COLORS[Math.floor(Math.random() * NOTE_COLORS.length)];
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
  const noteId = fragment.querySelector(".note-id");
  const deleteBtn = fragment.querySelector(".note-delete");

  noteEl.dataset.id = note.id;
  noteEl.style.left = `${note.x}px`;
  noteEl.style.top = `${note.y}px`;
  noteEl.style.background = note.color || pickRandomColor();
  textarea.value = note.text || "";
  
  if (noteId) {
    noteId.textContent = `MSG-${String(note.id).padStart(4, '0')}`;
  }
  
  if (authorEl) {
    authorEl.textContent = note.author_label ? `Agent:${note.author_label}` : "";
  }

  if (note.is_owner) {
    deleteBtn.style.display = "flex";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("Diese Nachricht löschen? / Delete this message?")) return;
      try {
        const resp = await fetch(`/api/notes/${note.id}`, { method: "DELETE" });
        if (!resp.ok) throw new Error(`${resp.status}`);
        noteEl.remove();
        showToast("Nachricht gelöscht / Message deleted");
      } catch (_err) {
        showToast("Löschen fehlgeschlagen / Delete failed");
      }
    });
  } else {
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
      alert("Bearbeitung fehlgeschlagen / Edit failed");
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
      li.textContent = "⚠ Keine Aufzeichnungen / No records found ⚠";
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
    historyList.innerHTML = `<li class="history-empty">Zugriff verweigert / Access denied</li>`;
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
    alert("Nachrichten konnten nicht geladen werden / Could not load messages");
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
  const time = formatClock(new Date());
  if (bigClock) bigClock.textContent = time;
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
      lastSummary.textContent = status.summary || "Warten auf Befehle... / Waiting for orders...";
    }
    updateGenerationCountdown();

    if (status.cycle_id && status.cycle_id !== currentCycleId) {
      if (currentCycleId !== null) {
        canvas.innerHTML = "";
        await loadNotes();
        loadHistory();
        showToast("Neue Operation gestartet / New operation started");
      }
      currentCycleId = status.cycle_id;
    }
  } catch (_error) {
    if (lastSummary) {
      lastSummary.textContent = "Status unbekannt / Status unknown";
    }
  }
}

function solvePow(challenge, difficulty) {
  return new Promise((resolve, reject) => {
    const worker = new Worker("/pow-worker.js");
    worker.onmessage = (e) => { worker.terminate(); resolve(e.data.nonce); };
    worker.onerror = (e) => { worker.terminate(); reject(new Error(e.message)); };
    worker.postMessage({ challenge, difficulty });
  });
}

async function createNewNote() {
  const text = window.prompt("Ihre Nachricht eingeben / Enter your message:", "");
  if (text === null || text.trim() === "") return;

  newNoteBtn.disabled = true;
  const origLabel = newNoteBtn.innerHTML;
  newNoteBtn.innerHTML = '<span class="deploy-brackets">[</span><span class="deploy-text">VERARBEITUNG... / PROCESSING...</span><span class="deploy-brackets">]</span>';
  
  try {
    const pow = await requestJson("/api/pow-challenge");
    showToast("Berechnung läuft... / Computing...");
    const nonce = await solvePow(pow.challenge, pow.difficulty_submit);

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
    setTimeout(() => noteEl.classList.remove("just-added"), 800);
    
    const message = note.author_label ? `Gesendet als ${note.author_label} / Sent as ${note.author_label}` : "Nachricht gesendet / Message sent";
    showToast(message);
  } catch (_error) {
    alert("Senden fehlgeschlagen / Send failed");
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
  const x = Math.max(0, Math.round(event.clientX - rect.left - 140));
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
    alert("Verschiebung fehlgeschlagen / Move failed");
  }
});

newNoteBtn.addEventListener("click", createNewNote);

requestJson("/api/cycle/current").then((c) => { currentCycleId = c.cycle_id || null; }).catch(() => {});

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
