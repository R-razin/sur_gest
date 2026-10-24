# AirControl AI — Motion gestures and 128 synthetic slices

## Changes
- Four visually distinct mathematical (NOT patient) phantom series of 32 slices each; total 128.
- Click the four Series selectors under the image viewer to jump to a series.
- **Real motion**: Camera mode + Start camera + Activate control. Move an open palm deliberately from LEFT to RIGHT across the camera preview to go to the next slice. Move RIGHT to LEFT to go to previous slice. A swipe needs ~22% frame-width travel across at least 4 frames; keep your hand visible and roughly level. Hold the hand still afterward.
- Motion recognition is separate from static KNN pose recognition: you do not need to enroll a swipe. Other static gestures (fist / open palm) still require camera-based enrollment to work with the webcam.
- Backend checks armed state, only accepts camera motion, rate-limits swipe commands, and logs them. Manual buttons and keyboard still work while paused.
- Swipe direction follows the mirrored camera preview. If your camera orientation behaves differently, reverse `next_slice` and `previous_slice` in `frontend/src/motion.ts`.

## Installation
Copy `backend/app`, `backend/tests`, and `frontend/src` from this package into the matching project folders. Back up existing files first. No new npm or Python packages required.

Backend from the project root:
` .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 `

Frontend in a second terminal:
` cd frontend; npm.cmd run dev `

Open http://127.0.0.1:5173 . Select Camera, start camera, activate control, navigate to Imaging lab, and swipe across the preview. You need at least one enabled gesture mapping to arm the existing safety controller.

## Limitations
Motion requires detected MediaPipe hand landmarks across several frames and won't work if the hand exits the frame, changes direction often, is occluded, or moves too quickly for the polling rate. The video stream is processed on the local server. This is a demo, not validated clinical software. Dynamic motion is only implemented for horizontal swipes, not arbitrary moving gestures.
