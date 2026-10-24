# Verification record

## Automated

- Python: 22 tests passed (`python -m pytest -q`). Covers backend core logic, invalid input, safety, stale frame cancellation, minimum frame count, API, evaluation and the complete synthetic workflow.
- Frontend: 3 tests passed (`npm test`). Camera permission denial, backend/model error messages, and generic device failure fallback.
- TypeScript and Vite production build passed (`npm run build`); chart dependencies split into a separate bundle.
- Frontend npm audit reported zero vulnerabilities after updating Vitest to 5.0.5.
- A Starlette deprecation warning reports that its future test-client implementation prefers httpx2. Existing HTTPX tests pass.

## Browser acceptance

Verified in the local in-app browser:

- Empty dashboard uses no fabricated accuracy or latency.
- Enrollment collects 12 synthetic examples, shows a 9/3 training/test split, and confirms a saved mapping.
- Activation shows classifier confidence and candidate validation.
- A held open-palm gesture zooms the image from 100% to 115% exactly once.
- Noisy landmark input shows 0% confidence and an explicit rejection without changing zoom.
- Pause stops the recognition loop.
- Assistant proposes a valid `next_slice` mapping, confirmation saves it disabled, and explicit review enables it in Settings.
- Benchmark produces actual metrics (the tested enrollment yielded 33.3% held-out accuracy, rather than a fabricated perfect score), a baseline comparison, counts, replay duration, and limitations.

## Camera

Downloaded the versioned MediaPipe model. Model creation and a blank JPEG inference returned no hand, as expected, with pinned MediaPipe 0.10.21. No diagnostic network attempt appeared in that smoke-test output. `pip check` reported no broken requirements. Actual human webcam capture and recognition have not been verified. Missing-model and oversized-image failure paths are tested. Permissions are only requested when the user clicks Start camera; Stop camera explicitly releases tracks.

## Not verified

Physical webcam/device conditions, human accuracy across independent sessions, accessibility effectiveness for specific disabilities, comprehensive WCAG compliance, high-load or multi-user behavior, and fully offline execution. Dynamic gestures and clinical integration are not implemented.
