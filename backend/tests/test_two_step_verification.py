import pytest
from starlette.testclient import TestClient
from app.main import app, safety, viewer, profiles, get_verification_symbol
from app.schemas import Settings
from app.safety import SafeIntent
from app.features import synthetic, extract
from app.classifier import PersonalizedClassifier


S = Settings(threshold=0.10, dwell_ms=300, cooldown_ms=650)
OPEN = {'enabled': True, 'action': 'zoom_in', 'threshold': 0.10}
FIST = {'enabled': True, 'action': 'zoom_out', 'threshold': 0.10}
CONFIRM = {'enabled': True, 'action': 'confirm_pending', 'threshold': 0.10}
STOP = {'enabled': True, 'action': 'stop_zoom', 'threshold': 0.10}
PAUSE = {'enabled': True, 'action': 'pause_control', 'threshold': 0.10}
NEXT_SLICE = {'enabled': True, 'action': 'next_slice', 'threshold': 0.10}
PAN_LEFT = {'enabled': True, 'action': 'pan_left', 'threshold': 0.10}


def test_1_no_action_before_confirmation():
    """1. No gesture-driven image action must execute before confirmation."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    v = viewer.value['zoom']
    # Present Open palm for dwell duration
    for t in (0, 160, 320):
        r = gate.process('Open palm', 0.95, OPEN, S, t, source='camera')
    assert r['state'] == 'AWAITING_VERIFICATION'
    assert r['action'] is None
    assert gate.pending_intent is not None
    assert gate.pending_intent['pending_command'] == 'zoom_in'
    # Viewer zoom is unchanged
    assert viewer.value['zoom'] == v


def test_2_correct_confirmation_executes_exactly_once():
    """2. Correct confirmation executes the authorized action exactly once."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    # Request next_slice
    for t in (0, 150, 320):
        gate.process('Point', 0.95, NEXT_SLICE, S, t, source='camera')
    assert gate.state == 'AWAITING_VERIFICATION'

    # Fast verification: Present Thumbs Up confirmation gesture (>= 10% conf) executes immediately
    r1 = gate.process('Thumbs Up', 0.90, CONFIRM, S, 400, source='camera')
    assert r1['state'] == 'STOPPED'
    assert r1['action'] == 'next_slice'
    assert gate.pending_intent is None

    # Repeated frames with Thumbs Up must not execute again
    r2 = gate.process('Thumbs Up', 0.90, CONFIRM, S, 650, source='camera')
    assert r2['action'] is None
    r3 = gate.process('Thumbs Up', 0.90, CONFIRM, S, 950, source='camera')
    assert r3['action'] is None


def test_3_incorrect_verification_rejected():
    """3. Incorrect verification symbol is rejected; action remains pending."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    for t in (0, 150, 320):
        gate.process('Point', 0.95, NEXT_SLICE, S, t, source='camera')
    assert gate.state == 'AWAITING_VERIFICATION'

    # Show Peace or Fist instead of Thumbs Up
    r = gate.process('Peace', 0.95, {'enabled': True, 'action': 'previous_slice'}, S, 500, source='camera')
    assert r['state'] == 'AWAITING_VERIFICATION'
    assert r['reason_code'] == 'unexpected_verification_gesture'
    assert r['action'] is None
    assert gate.pending_intent['pending_command'] == 'next_slice'


def test_4_low_confidence_verification_rejected():
    """4. Confirmation with confidence below 0.10 is rejected."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    for t in (0, 150, 320):
        gate.process('Point', 0.95, NEXT_SLICE, S, t, source='camera')
    assert gate.state == 'AWAITING_VERIFICATION'

    # Thumbs Up with only 0.05 confidence (< 0.10 required)
    r = gate.process('Thumbs Up', 0.05, CONFIRM, S, 500, source='camera')
    assert r['state'] == 'AWAITING_VERIFICATION'
    assert r['reason_code'] == 'low_confidence_verification'
    assert r['action'] is None


def test_5_expired_pending_action_cancelled():
    """5. Pending action cancels automatically after 5-second deadline."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    for t in (0, 150, 320):
        gate.process('Point', 0.95, NEXT_SLICE, S, t, source='camera')
    assert gate.state == 'AWAITING_VERIFICATION'

    # Move past 5000 ms monotonic deadline
    r = gate.process(None, 0.0, None, S, 5400, source='camera')
    assert r['state'] == 'CANCELLED'
    assert r['reason_code'] == 'verification_expired'
    assert gate.pending_intent is None


def test_6_source_mismatch_rejected():
    """6. Verification from a mismatched input source is rejected."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    # Requested from camera
    for t in (0, 150, 320):
        gate.process('Point', 0.95, NEXT_SLICE, S, t, source='camera')
    assert gate.state == 'AWAITING_VERIFICATION'

    # Confirmation sent from simulation
    r = gate.process('Thumbs Up', 0.95, CONFIRM, S, 500, source='simulation')
    assert r['state'] == 'AWAITING_VERIFICATION'
    assert r['reason_code'] == 'source_mismatch'
    assert r['action'] is None


def test_7_original_action_cannot_self_confirm():
    """7. The initiating gesture cannot confirm itself."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    for t in (0, 150, 320):
        gate.process('Open palm', 0.95, OPEN, S, t, source='camera')
    assert gate.state == 'AWAITING_VERIFICATION'

    # User presents Open palm again during verification
    r = gate.process('Open palm', 0.95, OPEN, S, 500, source='camera')
    assert r['state'] == 'AWAITING_VERIFICATION'
    assert r['reason_code'] == 'self_confirm_rejected'
    assert r['action'] is None


def test_8_repeated_frames_do_not_double_execute():
    """8. Confirmed discrete action executes exactly once; repeated frames do not duplicate."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    for t in (0, 150, 320):
        gate.process('Point', 0.95, PAN_LEFT, S, t, source='camera')
    executed = []
    for t in (400, 650, 950):
        r = gate.process('Thumbs Up', 0.90, CONFIRM, S, t, source='camera')
        if r['action']:
            executed.append(r['action'])
    assert executed == ['pan_left']

    # Subsequent frames
    for t in (1000, 1100, 1200, 1300):
        r2 = gate.process('Thumbs Up', 0.90, CONFIRM, S, t, source='camera')
        assert r2['action'] is None


def test_9_swipe_requires_verification():
    """9. Dynamic motion swipes require two-step verification before modifying the image."""
    with TestClient(app) as c:
        c.delete('/api/data')
        # Enroll test gestures
        c.post('/api/enroll', json={
            'mapping': {'gesture_label': 'Thumbs Up', 'action': 'confirm_pending', 'enabled': True},
            'samples': [{'source': 'camera', 'landmarks': synthetic(5, i)} for i in range(12)],
            'elapsed_seconds': 2.0
        })
        c.post('/api/state', json={'state': 'ARMED'})
        initial_slice = c.get('/api/status').json()['viewer']['slice']

        # Send swipe request
        r = c.post('/api/motion', json={'action': 'next_slice', 'source': 'camera'})
        assert r.status_code == 200
        data = r.json()
        assert data['state'] == 'AWAITING_VERIFICATION'
        assert data['pending_verification'] is not None
        assert data['pending_verification']['pending_command'] == 'next_slice'
        # Viewer slice MUST NOT have changed before confirmation!
        assert data['viewer']['slice'] == initial_slice


def test_10_continuous_zoom_requires_returning_to_original_gesture():
    """10. Continuous zoom requires returning to the original gesture after confirmation."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    # Step 1: Request zoom_in with Open palm
    for t in (0, 150, 320):
        gate.process('Open palm', 0.95, OPEN, S, t, source='camera')
    assert gate.state == 'AWAITING_VERIFICATION'

    # Step 2: Confirm with Thumbs Up
    for t in (400, 650, 950):
        r = gate.process('Thumbs Up', 0.90, CONFIRM, S, t, source='camera')
    assert r['state'] == 'VERIFIED'
    assert 'show Open palm again to begin' in r['reason']

    # Step 3: Presenting Fist or Peace does NOT begin zoom
    r_wrong = gate.process('Fist', 0.90, FIST, S, 1100, source='camera')
    assert r_wrong['state'] == 'VERIFIED'
    assert r_wrong['action'] is None

    # Step 4: Presenting Open palm starts continuous zoom!
    r_start = gate.process('Open palm', 0.90, OPEN, S, 1300, source='camera')
    r_start2 = gate.process('Open palm', 0.90, OPEN, S, 1450, source='camera')
    assert r_start2['state'] == 'ACTIVE_CONTINUOUS'
    assert r_start2['action'] == 'zoom_in'


def test_11_continuous_zoom_stops_when_hand_tracking_is_lost():
    """11. Continuous zoom stops immediately if hand tracking is lost or frame is stale."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    for t in (0, 150, 320): gate.process('Open palm', 0.95, OPEN, S, t, source='camera')
    for t in (400, 650, 950): gate.process('Thumbs Up', 0.90, CONFIRM, S, t, source='camera')
    gate.process('Open palm', 0.90, OPEN, S, 1100, source='camera')
    gate.process('Open palm', 0.90, OPEN, S, 1250, source='camera')
    assert gate.state == 'ACTIVE_CONTINUOUS'

    # Tracking lost (label=None)
    r_lost = gate.process(None, 0.0, None, S, 1350, source='camera')
    assert r_lost['state'] == 'STOPPED'
    assert gate.continuous_session is None

    # Returning hand does NOT resume zoom without fresh two-step verification
    r_return = gate.process('Open palm', 0.90, OPEN, S, 2100, source='camera')
    assert r_return['action'] is None
    assert r_return['state'] in ('ARMED', 'ACTION_CANDIDATE')


def test_12_stop_zoom_and_emergency_pause_work_immediately():
    """12. Stop Zoom and Emergency Pause work immediately without verification."""
    gate = SafeIntent()
    gate.set_state('ARMED')

    # Emergency pause works immediately
    r_pause = gate.process('Pause pose', 0.90, PAUSE, S, 400, source='camera')
    assert r_pause['state'] == 'PAUSED'
    assert r_pause['action'] == 'pause_control'

    # Arm and test stop_zoom
    gate.set_state('ARMED')
    for t in (0, 150, 320): gate.process('Open palm', 0.95, OPEN, S, t, source='camera')
    for t in (400, 650, 950): gate.process('Thumbs Up', 0.90, CONFIRM, S, t, source='camera')
    gate.process('Open palm', 0.90, OPEN, S, 1100, source='camera')
    gate.process('Open palm', 0.90, OPEN, S, 1250, source='camera')
    assert gate.state == 'ACTIVE_CONTINUOUS'

    # Stop zoom stops immediately
    r_stop = gate.process('Stop pose', 0.95, STOP, S, 1400, source='camera')
    assert r_stop['state'] == 'STOPPED'
    assert r_stop['action'] == 'stop_zoom'


def test_13_different_pending_actions_cannot_overlap():
    """13. While verification is pending, other actions cannot overlap or queue."""
    gate = SafeIntent()
    gate.set_state('ARMED')
    for t in (0, 150, 320): gate.process('Open palm', 0.95, OPEN, S, t, source='camera')
    assert gate.state == 'AWAITING_VERIFICATION'
    assert gate.pending_intent['pending_command'] == 'zoom_in'

    # User attempts to trigger Fist (zoom_out) while zoom_in is pending
    for t in (400, 550, 750):
        r = gate.process('Fist', 0.95, FIST, S, t, source='camera')
        assert r['state'] == 'AWAITING_VERIFICATION'
        assert r['action'] is None

    # Original pending command is still zoom_in
    assert gate.pending_intent['pending_command'] == 'zoom_in'


def test_14_existing_gesture_classification_and_training_still_work():
    """14. Invariant feature extraction and Personalized KNN classifier function properly."""
    clf = PersonalizedClassifier()
    samples = []
    # Train 3 distinct poses: 0 (Open palm), 1 (Fist), 5 (Thumbs up)
    for i in range(12):
        samples.append({'landmarks': synthetic(0, i), 'label': 'Open palm'})
        samples.append({'landmarks': synthetic(1, i), 'label': 'Fist'})
        samples.append({'landmarks': synthetic(5, i), 'label': 'Thumbs up'})
    clf.train(samples)

    pred_open, conf_open = clf.predict(synthetic(0, 999))
    assert pred_open == 'Open palm'
    assert conf_open > 0.80

    pred_fist, conf_fist = clf.predict(synthetic(1, 999))
    assert pred_fist == 'Fist'
    assert conf_fist > 0.80

    pred_thumb, conf_thumb = clf.predict(synthetic(5, 999))
    assert pred_thumb == 'Thumbs up'
    assert conf_thumb > 0.85


def test_15_backend_and_frontend_integration_remains_compatible(monkeypatch):
    """15. Status payload, pending verification details, and cancel endpoint operate cleanly."""
    from app import main
    now = [1000.0]
    monkeypatch.setattr(main.time, 'monotonic', lambda: now[0])
    with TestClient(app) as c:
        c.delete('/api/data')
        c.post('/api/enroll', json={
            'mapping': {'gesture_label': 'Open palm', 'action': 'zoom_in', 'enabled': True},
            'samples': [{'source': 'simulation', 'landmarks': synthetic(0, i)} for i in range(12)],
            'elapsed_seconds': 2.0
        })
        c.post('/api/enroll', json={
            'mapping': {'gesture_label': 'Thumbs up', 'action': 'confirm_pending', 'enabled': True},
            'samples': [{'source': 'simulation', 'landmarks': synthetic(5, i)} for i in range(12)],
            'elapsed_seconds': 2.0
        })
        c.post('/api/state', json={'state': 'ARMED'})

        # Trigger candidate and pass dwell timing (>= 300ms)
        for i in range(5):
            now[0] += 0.12
            c.post('/api/recognize', json={'source': 'simulation', 'landmarks': synthetic(0, 100 + i)})

        status = c.get('/api/status').json()
        assert status['state'] == 'AWAITING_VERIFICATION'
        assert status['pending_verification'] is not None
        assert status['pending_verification']['pending_command'] == 'zoom_in'
        assert 'prompt' in status['pending_verification']

        # Cancel verification via dedicated endpoint
        cancel_resp = c.post('/api/verification/cancel')
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()['state'] == 'CANCELLED'
        assert cancel_resp.json()['pending_verification'] is None
