import os
os.environ['AIRCONTROL_DB'] = ':memory:'
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.features import synthetic

@pytest.fixture
def client():
    with TestClient(app) as c:
        c.delete('/api/data')
        yield c

def make_samples(pose: int, count: int = 12):
    return [{'landmarks': synthetic(pose, i), 'source': 'simulation'} for i in range(count)]

def enroll_gesture(client, label: str, pose: int, action: str = 'zoom_in', enabled: bool = True):
    return client.post('/api/enroll', json={
        'mapping': {
            'gesture_label': label,
            'action': action,
            'enabled': enabled,
            'requires_confirmation': True,
            'description': f'Test gesture {label}',
            'gesture_type': 'static',
            'accessibility_notes': 'None',
            'verified': True
        },
        'samples': make_samples(pose, 12),
        'elapsed_seconds': 4.5
    })

def test_user_defined_gesture_label_and_metadata(client):
    r = enroll_gesture(client, 'My Custom Gesture', 0, action='zoom_in', enabled=True)
    assert r.status_code == 200
    status = client.get('/api/status').json()
    assert len(status['profiles']) == 1
    p = status['profiles'][0]
    assert p['label'] == 'My Custom Gesture'
    assert p['description'] == 'Test gesture My Custom Gesture'
    assert p['gesture_type'] == 'static'
    assert p['mapping']['enabled'] is True

def test_action_registry_including_pause_control(client):
    r = enroll_gesture(client, 'Emergency Freeze', 1, action='pause_control', enabled=True)
    assert r.status_code == 200
    assert r.json()['profiles'][0]['mapping']['action'] == 'pause_control'

def test_assistant_propose_and_explanation(client):
    enroll_gesture(client, 'My Slice', 2, action='next_slice')
    r = client.post('/api/assistant/propose', json={
        'text': 'move forward to the next image slice',
        'gesture_label': 'My Slice'
    })
    assert r.status_code == 200
    data = r.json()
    assert data['action'] == 'next_slice'
    assert data['explanation'] != ''
    assert 'Advances forward' in data['explanation']

def test_direct_activation_without_verification_block(client):
    enroll_gesture(client, 'Fast Pose', 0, action='zoom_in', enabled=False)
    
    # Activating directly succeeds without verification roadblocks
    r = client.put('/api/profiles/Fast%20Pose', json={
        'enabled': True
    })
    assert r.status_code == 200
    p = client.get('/api/status').json()['profiles'][0]
    assert p['mapping']['enabled'] is True

def test_direct_action_update_and_sample_addition(client):
    enroll_gesture(client, 'Stable Pose', 0, action='zoom_in', enabled=True)
    p = client.get('/api/status').json()['profiles'][0]
    assert p['mapping']['enabled'] is True

    # Changing action directly updates the mapping
    r = client.put('/api/profiles/Stable%20Pose', json={
        'action': 'zoom_out'
    })
    assert r.status_code == 200
    p = r.json()['profiles'][0]
    assert p['mapping']['action'] == 'zoom_out'
    assert p['mapping']['enabled'] is True

    # Adding samples works smoothly and keeps profile intact
    r = client.post('/api/profiles/Stable%20Pose/samples', json={
        'samples': make_samples(0, 4),
        'source': 'simulation'
    })
    assert r.status_code == 200
    p = r.json()['profiles'][0]
    assert p['training_count'] == 12  # 9 original + 3 new training
