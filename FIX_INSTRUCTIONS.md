# AirControl AI — Fist zoom-out fix (0.10 threshold)

This package uses the **0.10 (10%) global threshold** from your last request.

## Installation (Windows)

1. Back up your existing `Vibeathon` folder / database.
2. Copy `backend/app/safety.py`, `backend/app/main.py`, `backend/app/schemas.py`, `frontend/src/App.tsx`, and `sample-config.json` to the matching paths in your project. The archive also contains complete support source files and a regression test.
3. Restart backend and frontend **from the Vibeathon root**:
   - backend: `.\scripts\start-backend.ps1`
   - frontend: `.\scripts\start-frontend.ps1`
4. In Settings & privacy, set and save the global confidence threshold to **0.10**. Stored SQLite settings override source defaults.
5. In Gesture Lab verify there is an ENABLED profile for `Fist` mapped to **Zoom out**. It must be trained using **camera** input if you are testing with a real hand, not merely synthetic samples.
6. In live control: hold a fist for at least 450 ms across >=3 stable frames. After performing another pose, allow the 900 ms cooldown. The updated controller permits a clearly different recognized gesture after cooldown without requiring a hand-out-of-frame release. The same held gesture still runs only once until released or a different gesture occurs.
7. If it still does not work, consult **Recognition status**: it now displays the detected label, action, enabled status, input source and *effective per-gesture/global threshold*. Check the SafeIntent reason and verify the displayed mapping is `Zoom out`.

## Files changed
- `backend/app/safety.py`: permit distinct label transitions after cooldown with full confidence/dwell/stability checks; keep same-pose duplicate protection.
- `backend/app/main.py`: ensure emergency pause remains PAUSED; display source mismatch reason.
- `backend/app/schemas.py`: default and minimum thresholds 0.10.
- `frontend/src/App.tsx`: show effective mapped action and threshold plus live guidance.
- `sample-config.json`: example threshold 0.10.
- `backend/tests/test_fist_transition.py`: regression tests.

**Safety:** A 10% threshold makes false recognition more likely. Test on the synthetic phantom only; this is not a clinical device.
