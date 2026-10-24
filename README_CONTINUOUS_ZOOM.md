# AirControl AI: safe continuous zoom

## Behavior

- Enroll **Open palm** with `zoom_in` and **Fist** with `zoom_out` using the same active input source (Camera vs Simulation).
- Enroll a distinct **Peace** (two fingers) profile with action `stop_zoom`. The Stop zoom action is available in Gesture Lab and Settings. Camera gestures need CAMERA enrollment; synthetic gestures are source-isolated.
- After 3 consecutive valid frames and the configured dwell period, the first zoom step fires. Keeping that **same confident pose visible** produces additional 15%-scale zoom steps at **most once per 500 ms** and only after 3 stable frames per step.
- Zoom stops immediately on a different recognized pose, weak confidence, missing hand, paused system, or any frame gap greater than 750 ms. The next gesture needs independent candidate validation; Stop zoom explicitly ends the operation while keeping control ARMED.
- Zoom is bounded by the existing viewer minimum 0.5 and maximum 4.0. The large emergency **Pause recognition** button and `Esc` remain available.
- **Safety:** Even if the global confidence threshold is 0.10, automated zoom requires at least 0.70, or a higher per-gesture threshold. Never use 10% alone to drive repeating commands.
- No autonomous background timer is used. Commands only run while fresh landmark frames arrive and pass validation. Browser visibility/camera errors stop new commands. This is a demo prototype, not a clinical system.

## Install

From `C:\Users\moham\OneDrive\Desktop\Vibeathon`, back up your project and extract this ZIP into the same directory, preserving folders.

Backend (PowerShell, project root):
```
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Frontend (second terminal):
```
cd frontend
npm.cmd run dev
```

Open http://127.0.0.1:5173; reload the browser, verify the three active mappings, select Camera and start it, then Activate control. **Existing saved profiles must include a newly enrolled Stop zoom pose.**

## Verification

`PYTHONPATH=backend python -m pytest -q backend/tests` -> 47 passed in the isolated working environment. Live webcam operation and frontend build were not verified here.
