# AirControl AI — gesture recognition and action consistency repair

## Changes
- Camera and Simulation train separate live KNN classifiers; samples from one source never dominate predictions for the other source.
- The recognition endpoint validates landmarks even if there is no classifier yet and displays a clear message when that input source has no enrolled profiles.
- Removed the forced 80% confidence for any geometry-detected fist. Confidence now reflects the enrolled model, while hand posture is used as an independent veto against obvious reversed zoom mappings.
- A sudden open-palm ↔ fist change is not blended by smoothing into an imaginary intermediate gesture.
- The input loop no longer skips static recognition every time the swipe detector notices hand motion. When a swipe is actually accepted, it sends a release frame to cancel continuous zoom before changing the image.
- Additional enrollment samples must match the original profile's input source.
- Benchmark classification uses the correct source-specific model.
- Added regression tests for the complete five-gesture synthetic set and source separation.

## Install on Windows
1. Make a backup of your Vibeathon folder.
2. Extract this zip into C:\Users\moham\OneDrive\Desktop\Vibeathon, preserving paths.
3. Open PowerShell from that project root and start the backend **without running unsigned scripts**:
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
4. In another terminal:
   cd frontend
   npm.cmd ci
   npm.cmd run dev
5. Refresh http://127.0.0.1:5173 with Ctrl+Shift+R.
6. In Gesture Lab, ensure every profile is enabled and mapped to its intended action. **For the real camera, create Camera-mode profiles; simulation-only profiles cannot control the camera.**
7. If you changed feature-extraction code in earlier versions, enroll fresh independent samples of your actual gestures. Train with a steady pose, varied angles and lighting, and clearly different poses.
8. Keep zoom-in and zoom-out mappings consistent with the physical pose. Open palm = zoom_in, fist = zoom_out, optionally two-finger = stop_zoom.
9. Start in Simulation and verify each action, then try Camera. Camera results require real-hardware validation.

## How to diagnose a rejection
The Live Control recognition status shows the detected label, model confidence, enabled action, and safety reason. The configured global threshold is 10%, but continuous zoom intentionally uses a 70% minimum to reduce accidental repetitive movement. If the camera gesture scores below 70%, it will not continue zooming: add varied good-quality camera examples instead of lowering safety protections.

## Validation performed
54 Python backend tests passed in the analysis environment. The frontend production build was **not** verified: npm ci --offline failed because the dependency yallist-3.1.1 was absent from the local npm cache. Real-world webcam recognition and cross-user accuracy are **not** guaranteed or measured.

## Replaced files
backend/app/main.py
backend/app/features.py
frontend/src/App.tsx
backend/tests/test_core.py
backend/tests/test_recognition_integrity.py

The archive also includes the rest of the prior project tree to make matching locations easy. Files such as SQLite data, .venv, node_modules and the downloaded .task model are not bundled. Keep your local model and persisted data, and avoid placing sensitive live data in a OneDrive-synced folder.
