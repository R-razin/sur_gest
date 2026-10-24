AirControl AI threshold change: 0.82 -> 0.30

Copy files to matching project paths:
backend/app/schemas.py
frontend/src/App.tsx
sample-config.json

IMPORTANT: Existing SQLite settings may override the new default. Open Settings in the app, set Confidence threshold to 0.30, and Save recognition settings. Alternatively reset stored settings (may affect other saved settings).
Restart backend and frontend.
This lowers gesture rejection strictness and may increase accidental commands; test in simulation before camera use.
