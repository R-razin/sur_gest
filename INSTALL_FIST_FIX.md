# AirControl AI — Fist / Zoom out correction

## What was corrected
- Added a conservative four-finger geometric posture check. A clearly closed hand will not execute an open-palm zoom-in command.
- When a **camera-enrolled, enabled** `zoom_out` profile exists, a strongly closed hand may select it even if the personalized KNN model confused the label.
- The posture-based fallback reports a heuristic confidence of 80%; this is not calibrated recognition probability. It remains subject to the existing SafeIntent 70% minimum, dwell, repeat rate, and state checks.
- The UI now displays the actual effective zoom-confidence minimum (70%, or higher if configured) instead of showing only the global minimum (10%).
- Resetting to IDLE clears stale cooldown time; a restart/reset will not inhibit actions because of a previous run.
- Added tests for synthetic fist/open/partial poses, mirroring/rotation, safe zoom-out, and camera API path.

## Install
1. Back up your existing project directory first.
2. Extract this ZIP *into* `C:\Users\moham\OneDrive\Desktop\Vibeathon` and replace matching paths. Do **not** move all files into `frontend`.
3. From the project root run in terminal 1:
   `.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`
4. In terminal 2 run:
   `cd frontend; npm.cmd run dev`
5. Hard-refresh the browser (Ctrl+Shift+R).

## Crucial setup
- In **Gesture Lab**, enroll **Fist** in **Camera mode** (not Simulation). Enroll at least 12 varied camera samples of a clearly clenched fist, with good lighting, from the actual webcam. Save its action as `Zoom out`, and **enable** the profile.
- Also enroll **Open palm** in Camera mode, with `Zoom in` enabled, using distinct training examples.
- Camera mode only matches camera-enrolled profiles. If using synthetic simulation, enroll simulation profiles instead.
- Keep your full hand visible; wait for the initial dwell before zoom-out starts. Recognition must be ARMED and the viewer must be above 50% zoom.
- The displayed global 10% confidence threshold DOES NOT override the separate 70% continuous zoom safety minimum.
- Review `Recognition status` and `SafeIntent` reason when a gesture is blocked.

## Testing and limitations
- 51 Python backend tests passed locally, including a simulated camera-API fist-to-zoom-out test.
- The React build and *real human webcam capture* have not been validated here. Real hand occlusion, extreme angles, and low-quality landmarks can still cause errors.
- A four-finger heuristic can confuse other tightly curled poses with a fist. Always test with your webcam and do not use for clinical decisions.
