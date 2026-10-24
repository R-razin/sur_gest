from app.safety import SafeIntent
from app.schemas import Settings

ZOOM_IN = {'action': 'zoom_in', 'enabled': True, 'threshold': None}
ZOOM_OUT = {'action': 'zoom_out', 'enabled': True, 'threshold': None}
CONFIRM = {'action': 'confirm_pending', 'enabled': True, 'threshold': None}
S = Settings(threshold=0.10, dwell_ms=450, cooldown_ms=900)

def test_fist_after_palm_without_losing_hand():
    gate = SafeIntent(); gate.set_state('ARMED')
    assert gate.process('Open palm', .90, ZOOM_IN, S, 0)['action'] is None
    gate.process('Open palm', .90, ZOOM_IN, S, 200)
    r = gate.process('Open palm', .90, ZOOM_IN, S, 500)
    assert r['state'] == 'AWAITING_VERIFICATION'
    assert gate.pending_intent['pending_command'] == 'zoom_in'

def test_new_gesture_must_pass_its_own_threshold():
    gate = SafeIntent(); gate.set_state('ARMED')
    strict = dict(ZOOM_OUT, threshold=.75)
    assert gate.process('Fist', .60, strict, S, 1500)['action'] is None
    assert gate.process('Fist', .60, strict, S, 2000)['action'] is None

def test_release_allows_same_gesture_again():
    gate = SafeIntent(); gate.set_state('ARMED')
    for t in (0, 200, 500):
        r = gate.process('Fist', .9, ZOOM_OUT, S, t)
    assert r['state'] == 'AWAITING_VERIFICATION'
    gate.process(None, 0, None, S, 600)
    assert gate.state == 'AWAITING_VERIFICATION'
    assert gate.pending_intent['pending_command'] == 'zoom_out'
