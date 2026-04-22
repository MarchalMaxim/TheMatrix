const canvas = document.getElementById("canvas");
const newNoteBtn = document.getElementById("new-note-btn");
const noteTemplate = document.getElementById("note-template");
const bigClock = document.getElementById("big-clock");
const bigClock2 = document.getElementById("big-clock-2");
const generationCountdown = document.getElementById("generation-countdown");
const lastSummary = document.getElementById("last-summary");
const historyList = document.getElementById("history-list");

const NOTE_COLORS = [
  "var(--concrete)",
  "var(--concrete-light)",
  "#2d2d2d",
  "#323232",
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
    noteId.textContent = `PKT_${String(note.id).padStart(4, '0')}`;
  }
  
  if (authorEl) {
    authorEl.textContent = note.author_label ? `SRC:${note.author_label}` : "";
  }

  if (note.is_owner) {
    deleteBtn.style.display = "flex";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("PURGE THIS DATA PACKET?")) return;
      try {
        const resp = await fetch(`/api/notes/${note.id}`, { method: "DELETE" });
        if (!resp.ok) throw new Error(`${resp.status}`);
        noteEl.remove();
        showToast("PACKET_PURGED");
        if (window.industrialAudio) window.industrialAudio.noteDeleted();
      } catch (_err) {
        showToast("PURGE_FAILED");
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
      alert("TRANSMISSION_UPDATE_FAILED");
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
      li.textContent = "// NO_ENTRIES_FOUND";
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
    historyList.innerHTML = `<li class="history-empty">LOG_ACCESS_DENIED</li>`;
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
    alert("DATA_RETRIEVAL_FAILED");
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
  if (bigClock2) bigClock2.textContent = time;
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
      lastSummary.textContent = status.summary || "AWAITING_OPERATOR_INPUT...";
    }
    updateGenerationCountdown();

    if (status.cycle_id && status.cycle_id !== currentCycleId) {
      if (currentCycleId !== null) {
        canvas.innerHTML = "";
        await loadNotes();
        loadHistory();
        showToast("NEW_CYCLE_INITIATED");
      }
      currentCycleId = status.cycle_id;
    }
  } catch (_error) {
    if (lastSummary) {
      lastSummary.textContent = "STATUS_QUERY_FAILED";
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
  const text = window.prompt("ENTER_DATA_TRANSMISSION:", "");
  if (text === null || text.trim() === "") return;

  newNoteBtn.disabled = true;
  const origLabel = newNoteBtn.innerHTML;
  newNoteBtn.innerHTML = '<span class="button-inner"><span class="button-symbol">⚠</span><span>PROCESSING...</span></span>';
  
  try {
    const pow = await requestJson("/api/pow-challenge");
    showToast("COMPUTING_PROOF_OF_WORK...");
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
    setTimeout(() => noteEl.classList.remove("just-added"), 600);
    
    const message = note.author_label ? `TRANSMISSION_LOGGED_AS_${note.author_label}` : "PACKET_TRANSMITTED";
    showToast(message);
    
    if (window.industrialAudio) window.industrialAudio.noteCreated();
  } catch (_error) {
    alert("TRANSMISSION_FAILED");
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
  const x = Math.max(0, Math.round(event.clientX - rect.left - 120));
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
    alert("RELOCATION_FAILED");
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
