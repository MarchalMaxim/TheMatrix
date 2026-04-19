# TheMatrix

A whimsical little board where users can place post-it notes on a shared canvas.

## Run locally

```bash
python3 server.py
```

Then open <http://127.0.0.1:8000>.

## What happens every 15 minutes

A background worker collects all current post-its, creates a short summary of the suggestions, and writes a Copilot handoff artifact to:

- `worker/copilot_handoff/latest_handoff.json`
- `worker/copilot_handoff/copilot_task.md`
