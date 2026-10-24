# AirControl AI

**Touchless Precision. Uninterrupted Focus.**

A local, software-only research prototype built for Vibethon / ENCIDE, Mar Athanasius College of Engineering. React + TypeScript + Vite + Tailwind, FastAPI + SQLite, MediaPipe + OpenCV, NumPy + scikit-learn.

**This is not a clinically validated medical device, a surgical decision system, or a guarantee of surgical safety.** All actions affect an original synthetic image phantom. No patient data or hospital integration is involved.

## Run on Windows

Prerequisites: Node.js 22.12+ (tested with 26.3), Python 3.12, a modern browser. Run from this repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
cd frontend
npm.cmd ci
cd ..
```

For this machine, Python is available at:

```powershell
& 'C:\Users\moham\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
```

Start two terminals:

```powershell
# Terminal 1, repository root
.\scripts\start-backend.ps1
```

```powershell
# Terminal 2, repository root
.\scripts\start-frontend.ps1
```

Open **http://127.0.0.1:5173**. API documentation: **http://127.0.0.1:8000/docs**.

If PowerShell policy blocks a script, execute the corresponding commands directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# In a second terminal:
cd frontend
npm.cmd run dev
```

`requirements-lock.txt` records the tested Python 3.12 dependency versions. `requirements.txt` defines direct compatibility constraints for resolving on another platform. On macOS/Linux, use `python3 -m venv .venv`, `.venv/bin/python`, and `npm` in the equivalent commands.

The app uses efficient sequential HTTP frame requests (approximately 8 Hz plus inference time), rather than a WebSocket. The frontend development server proxies `/api` to FastAPI. Do not run multiple backend workers: this is a single-user, in-process safety controller with SQLite persistence.

## Webcam setup

Simulation needs no model download or camera permission. For live capture:

```powershell
.\scripts\download-model.ps1
```

This downloads Google's versioned Hand Landmarker task into `models/hand_landmarker.task`. The model is already downloaded in the delivered workspace. Select **Camera**, click **Start camera**, and allow access. Enroll camera examples separately from synthetic examples. Camera capture needs localhost or HTTPS. Camera JPEG frames go to the local FastAPI endpoint, are decoded with OpenCV, and are processed by MediaPipe in memory. Only landmarks are stored; video and image frames are not recorded.

Model absence, malformed images, no hand, and permission denial have explicit failure paths. A live human webcam session has not been verified in this environment. Blank-frame inference and model loading have been exercised.

## Configuration

No API key is needed. The setup assistant is a deterministic local parser. `.env.example` documents optional environment variables; the backend reads actual environment variables, not an automatically loaded `.env` file.

```powershell
$env:AIRCONTROL_DB = 'aircontrol.db'
$env:AIRCONTROL_MODEL = 'models/hand_landmarker.task'
```

Set these before starting the backend. Default paths are relative to the repository root. Settings and mappings are edited in **Settings & privacy**. `sample-config.json` illustrates the strict schemas; it contains no secrets.

## Implemented workflow

- Eight connected pages: overview, enrollment, live control, imaging lab, event log, benchmarks, assistant, settings/privacy.
- Enrollment of 12 examples through the UI; 9 used for training, 3 reserved for testing. API accepts 8–100 examples. Profiles can be replaced, deleted, remapped, calibrated, enabled, or disabled.
- Five repeatable synthetic static hand poses with seeded landmark noise. Live camera uses MediaPipe's 21 hand landmarks.
- Wrist-relative, palm-scale-normalized features, distance-weighted 3-neighbor KNN and distance-based unknown-pose rejection.
- Adjustable confidence threshold, smoothing, dwell, cooldown, sensitivity, and per-gesture confidence threshold.
- Separate SafeIntent state machine: confidence → stable consecutive predictions → dwell → cooldown → allowlist → execution. A held pose triggers once until no-hand release. Frame gaps over 750 ms reset the candidate.
- Thirty-two original mathematical axial phantom slices with zoom, pan, slice controls, reset, and undo. No third-party images or patient samples.
- Keyboard fallback: arrows change slices; `+`/`-` zoom; WASD pan; R resets; Esc pauses recognition.
- Session logs explain acceptance, rejection, and state changes. Latest 500 events and 20 benchmark reports persist locally; UI shows latest 100 events.
- Repeatable held-out benchmark replay with calculated command accuracy, macro precision/recall/F1, fixed-pose baseline, replay false activations/minute, candidate-to-action latency, enrollment time, and CSV/JSON exports.
- Local natural-language command parser with allowlist/schema validation and explicit confirmation before saving a disabled mapping.
- Local data deletion. Restricted origins, loopback-only server defaults, finite-number validation, bounded camera payloads, no uploaded files, no shell or OS command execution.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd test
npm.cmd run build
```

See [verification notes](docs/VERIFICATION.md) for tested flows and limitations. Backend tests cover feature invariance, degenerate/nonfinite input, classifier training, unknown rejection, thresholds, temporal stability, pause, duplicate suppression, cooldown, allowlists, assistant validation, viewer bounds/reset/undo, metrics, origin restrictions, source separation, and API failures. Frontend tests cover camera failure messages. The API end-to-end test covers enrollment → uncertain rejection → accepted action → held-out benchmark → assistant confirmation → pause.

## Honest limits

- Static hand poses only. Dynamic gestures, arbitrary-gesture support, rotation invariance, handedness adaptation, and disability-specific effectiveness are not established.
- Confidence is a KNN vote weighted by a landmark-distance heuristic, not a calibrated probability. Personalization may perform worse than the fixed baseline. Thresholds may need adjustment.
- Held-out examples come from the same enrollment session and are correlated. Synthetic results are not evidence of human or clinical performance. Collect independent user sessions before making effectiveness claims.
- The fixed baseline uses five mathematical pose templates with fixed viewer commands. It is a demonstration baseline, not a validated general-purpose recognizer.
- Benchmark duration and action latency are measured on an explicit replay timeline. These are not end-to-end webcam wall-clock latency or real-world false activation rates. JSON contains the underlying labeled predictions.
- No real DICOM/NIfTI ingestion, patient data, custom hardware, or medical-system connection.
- Single local user only; no authentication or encrypted database. Do not expose the server on a public interface.
- Dependency/model installation requires internet. Fully offline operation has not been independently verified. Camera permission, camera availability, and actual human recognition depend on the local device.
- Persistent data is stored under the selected workspace. If that directory is synchronized by OneDrive or another file-sync service, that service may synchronize the SQLite database. Use `AIRCONTROL_DB` to select a nonsynchronized local path for private use.

See [architecture](docs/ARCHITECTURE.md) and the [demo script](docs/DEMO.md).
