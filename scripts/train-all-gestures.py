"""
Automated training script for AirControl AI.

Enrolls all 5 synthetic gesture poses via the /api/enroll endpoint,
then runs the benchmark to evaluate the trained classifier.

Usage:
    python scripts/train-all-gestures.py

The backend must be running at http://127.0.0.1:8000 before executing this.
"""

import sys
import os
import time
import httpx

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"

# ── Gesture definitions ────────────────────────────────────────────
# Each maps a synthetic pose index (0-4) to a label and viewer command.
# Pose patterns (from features.py):
#   0: all fingers extended  → Open palm   → zoom_in
#   1: all fingers closed    → Fist        → zoom_out
#   2: index finger only     → Point       → next_slice
#   3: index + middle        → Peace       → previous_slice
#   4: thumb + pinky          → Shaka       → reset_view
GESTURES = [
    {"pose": 0, "label": "Open palm",  "action": "zoom_in"},
    {"pose": 1, "label": "Fist",       "action": "zoom_out"},
    {"pose": 2, "label": "Point",      "action": "next_slice"},
    {"pose": 3, "label": "Peace",      "action": "previous_slice"},
    {"pose": 4, "label": "Shaka",      "action": "reset_view"},
    {"pose": 5, "label": "Thumbs up",  "action": "confirm_pending"},
]

SAMPLES_PER_GESTURE = 12  # minimum 8 required; 12 gives 9 train + 3 test


def check_server(client: httpx.Client) -> bool:
    """Verify the backend is reachable."""
    try:
        r = client.get(f"{BASE}/api/status")
        r.raise_for_status()
        return True
    except (httpx.ConnectError, httpx.HTTPStatusError):
        return False


def generate_samples(client: httpx.Client, pose: int, count: int) -> list[dict]:
    """Generate synthetic landmark samples using the /api/simulation endpoint."""
    samples = []
    for seed in range(count):
        r = client.get(f"{BASE}/api/simulation/{pose}", params={"seed": seed})
        r.raise_for_status()
        landmarks = r.json()["landmarks"]
        samples.append({"landmarks": landmarks, "source": "simulation"})
    return samples


def enroll_gesture(
    client: httpx.Client, label: str, action: str, samples: list[dict]
) -> dict:
    """Enroll a gesture via POST /api/enroll."""
    payload = {
        "mapping": {
            "gesture_label": label,
            "action": action,
            "requires_confirmation": True,
            "enabled": True,
            "threshold": None,
        },
        "samples": samples,
        "elapsed_seconds": 5.0,
    }
    r = client.post(f"{BASE}/api/enroll", json=payload)
    r.raise_for_status()
    return r.json()


def run_benchmark(client: httpx.Client) -> dict:
    """Run the held-out benchmark evaluation."""
    r = client.post(f"{BASE}/api/benchmark")
    r.raise_for_status()
    return r.json()


def main():
    print("=" * 60)
    print("  AirControl AI  —  Automated Gesture Training")
    print("=" * 60)
    print()

    client = httpx.Client(timeout=30)

    # 1. Check server
    print("→ Checking backend at", BASE, "...")
    if not check_server(client):
        print(
            "\n✗ Backend is not running. Start it first with:\n"
            "  .\\.venv\\Scripts\\python.exe -m uvicorn app.main:app "
            "--app-dir backend --host 127.0.0.1 --port 8000\n"
        )
        sys.exit(1)
    print("  ✓ Backend is online.\n")

    # 2. Enroll each gesture
    for g in GESTURES:
        pose, label, action = g["pose"], g["label"], g["action"]
        print(f"→ Enrolling '{label}' (pose {pose}) → {action}")
        print(f"  Generating {SAMPLES_PER_GESTURE} synthetic samples...", end=" ")
        samples = generate_samples(client, pose, SAMPLES_PER_GESTURE)
        print("done.")

        print("  Training classifier...", end=" ")
        start = time.perf_counter()
        result = enroll_gesture(client, label, action, samples)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"done ({elapsed:.0f} ms).")

        profiles = result.get("profiles", [])
        for p in profiles:
            if p["label"] == label:
                print(
                    f"  ✓ {p['training_count']} training / "
                    f"{p['test_count']} test examples enrolled."
                )
                break
        print()

    # 3. Summary
    status = client.get(f"{BASE}/api/status").json()
    profiles = status.get("profiles", [])
    print("─" * 60)
    print(f"  Enrolled {len(profiles)} gesture profiles:")
    for p in profiles:
        enabled = "✓" if p.get("mapping", {}).get("enabled") else "✗"
        print(
            f"    [{enabled}] {p['label']:15s} → {p['mapping']['action']:20s} "
            f"({p['training_count']} train, {p['test_count']} test)"
        )
    print(f"\n  Model ready: {status.get('model_ready', False)}")
    print()

    # 4. Run benchmark
    print("→ Running held-out benchmark evaluation...")
    bench = run_benchmark(client)
    pm = bench.get("personalized", {})
    bm = bench.get("baseline", {})
    gm = bench.get("gesture_metrics", {})
    ev = bench.get("events", {})

    print()
    print("─" * 60)
    print("  BENCHMARK RESULTS")
    print("─" * 60)
    print(f"  Test samples:       {bench.get('sample_count', '?')}")
    print(f"  Replay duration:    {bench.get('duration_seconds', '?'):.1f}s")
    print()
    print("  Personalized command accuracy:")
    print(f"    Accuracy:    {pm.get('accuracy', 0):.1%}")
    print(f"    Precision:   {pm.get('precision', 0):.1%}")
    print(f"    Recall:      {pm.get('recall', 0):.1%}")
    print(f"    F1 Score:    {pm.get('f1', 0):.1%}")
    print()
    print("  Gesture classification:")
    print(f"    Accuracy:    {gm.get('accuracy', 0):.1%}")
    print(f"    Precision:   {gm.get('precision', 0):.1%}")
    print(f"    Recall:      {gm.get('recall', 0):.1%}")
    print(f"    F1 Score:    {gm.get('f1', 0):.1%}")
    print()
    print("  Fixed baseline accuracy:")
    print(f"    Accuracy:    {bm.get('accuracy', 0):.1%}")
    print()
    print("  Replay events:")
    print(f"    Accepted:    {ev.get('accepted', 0)}")
    print(f"    Rejected:    {ev.get('rejected', 0)}")
    lat = ev.get("median_latency_ms")
    print(f"    Median lat:  {lat:.0f} ms" if lat else "    Median lat:  N/A")
    fa = ev.get("false_activations_per_minute")
    print(f"    False act/m: {fa:.2f}" if fa is not None else "    False act/m: N/A")
    print()

    # 5. Arm the system
    print("→ Arming the system for live gesture control...")
    r = client.post(f"{BASE}/api/state", json={"state": "ARMED"})
    if r.status_code == 200:
        print("  ✓ System is ARMED and ready for gesture recognition.\n")
    else:
        print(f"  ⚠ Could not arm: {r.text}\n")

    print("=" * 60)
    print("  Training complete! Open http://127.0.0.1:5173 to use.")
    print("=" * 60)


if __name__ == "__main__":
    main()
