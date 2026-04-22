// Intelligence page JavaScript - displays live stats

async function fetchNoteCount() {
  try {
    const notes = await fetch('/api/notes').then(r => r.json());
    const countEl = document.getElementById('note-count');
    if (countEl) {
      countEl.textContent = notes.length;
    }
  } catch (err) {
    const countEl = document.getElementById('note-count');
    if (countEl) {
      countEl.textContent = '???';
    }
  }
}

async function fetchCycleId() {
  try {
    const data = await fetch('/api/cycle/current').then(r => r.json());
    const idEl = document.getElementById('cycle-id');
    if (idEl && data.cycle_id) {
      idEl.textContent = data.cycle_id.substring(0, 12).toUpperCase();
    }
  } catch (err) {
    const idEl = document.getElementById('cycle-id');
    if (idEl) {
      idEl.textContent = 'UNKNOWN';
    }
  }
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

let nextRunEpochMs = null;

function updateCountdown() {
  const countdownEl = document.getElementById('intel-countdown');
  if (!countdownEl) return;
  
  if (typeof nextRunEpochMs !== "number") {
    countdownEl.textContent = "4:00:00";
    return;
  }

  const seconds = Math.max(0, Math.ceil((nextRunEpochMs - Date.now()) / 1000));
  countdownEl.textContent = formatCountdown(seconds);
}

async function refreshWorkerStatus() {
  try {
    const status = await fetch('/api/worker-status').then(r => r.json());
    nextRunEpochMs = typeof status.next_run_epoch === "number" ? status.next_run_epoch * 1000 : null;
    updateCountdown();
  } catch (err) {
    // Silent fail
  }
}

// Initialize
fetchNoteCount();
fetchCycleId();
refreshWorkerStatus();

// Update periodically
setInterval(updateCountdown, 1000);
setInterval(() => {
  fetchNoteCount();
  refreshWorkerStatus();
}, 15000);
