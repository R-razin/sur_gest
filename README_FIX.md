# AirControl AI — 96 synthetic slices + easier recognition

Install over your existing Vibeathon project, preserving folder structure. Back up your files first.

Changes:
- 96 synthetic axial slices (three visually distinct mathematical series, 32 each), instead of 32. These are NOT medical scans.
- Backend slice navigation and reset expanded to 0–95; frontend counters and canvas descriptions updated.
- Default threshold remains 0.10; smoother 0.20, dwell 300 ms, cooldown 650 ms, sensitivity 1.35. Recognition remains subject to safety checks.
- Expanded maximum sensitivity to 2.0 in Settings and server validation.
- Keeps prior multi-angle landmarks and different-gesture transition improvements.

IMPORTANT: Existing settings stored in aircontrol.db override new defaults. In Settings & privacy set threshold 0.10, smoothing 0.20, dwell 300, cooldown 650, sensitivity 1.35, and save. Ensure fist/open palm are ENROLLED and ENABLED in the same input mode (Camera vs Simulation).

Run from project root:
Backend: .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
Frontend: cd frontend; npm.cmd run dev

No change can guarantee detection from every angle/person; hand occlusion and classification ambiguity still matter. Test in simulation before using live camera.
