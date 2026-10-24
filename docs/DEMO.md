# Five-minute demonstration

1. Start both servers and open localhost:5173. Point out **Simulation mode**, **Research prototype**, and the synthetic imaging disclaimer.
2. Open **Gesture enrollment**. Keep the label **Open palm**, command **Zoom in**, and synthetic pose **Open palm**. Continue, capture 12 examples, review the 9/3 split, and confirm training.
3. In **Live gesture control**, activate control and click **Present gesture**. Observe classifier confidence and CANDIDATE → EXECUTED. Zoom changes from 100% to 115%. Leave it held: no repeated zoom should occur.
4. Click **Release hand**. Enable **Add landmark noise**, then present again. Confidence falls below the threshold, the reason explains rejection, and zoom stays unchanged.
5. Pause. Use manual slice/zoom/pan controls and Undo. Explain that manual fallback remains available while gesture execution is paused. Arrows, +/−, WASD, R and Esc are keyboard alternatives.
6. Open **SafeIntent event log** and inspect the accepted action and rejected prediction. Source, confidence, reason and state are visible; JSON export contains full stored events.
7. Open **Benchmark studio** and run an evaluation. Explain the actual held-out accuracy, baseline comparison, test count and replay duration. Do not promise a high score; with only three held-out samples, results can vary substantially. Review limitations and export CSV/JSON.
8. Open **AI setup assistant**, select **Open palm**, and ask “move to the next image slice.” Review the generated disabled mapping and confirm it. In **Settings & privacy**, enable the mapping explicitly. Re-arm to test it; remember to turn off injected landmark noise and release between actions.
9. Press **Esc**. Confirm PAUSED and no further gesture-driven actions. The manual viewer remains available.

Optional live branch: switch to Camera, start the camera and grant permission, enroll a **new camera profile** with real landmarks, review/enable it, and activate. Synthetic profiles are never applied to webcam input. If the model or camera is unavailable, the app reports the error; use Simulation without pretending the webcam succeeded.

Final statement: “AirControl AI is a software research prototype. These are synthetic images and replay results, not clinical validation.”
