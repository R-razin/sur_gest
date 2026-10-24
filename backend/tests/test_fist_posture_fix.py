import numpy as np
from app.features import finger_posture, synthetic
from app.safety import SafeIntent
from app.schemas import Settings


def test_posture_cues_on_all_five_poses():
    assert finger_posture(synthetic(0)) == 'open'
    assert finger_posture(synthetic(1)) == 'fist'
    for pose in (2, 3, 4):
        assert finger_posture(synthetic(pose)) == 'uncertain'


def test_fist_cue_invariant_to_rotation_and_mirror():
    points = np.asarray(synthetic(1))
    angle = .8
    rot = np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
    assert finger_posture(points @ rot.T * 2 + 5) == 'fist'
    assert finger_posture(points * [-1,1,1]) == 'fist'


def test_fist_must_pass_dwell_and_zoom_gate():
    gate=SafeIntent();gate.set_state('ARMED')
    mapping={'action':'zoom_out','enabled':True,'threshold':None}
    settings=Settings(threshold=.1,dwell_ms=300,cooldown_ms=650)
    assert gate.process('Fist',.80,mapping,settings,0)['action'] is None
    assert gate.process('Fist',.80,mapping,settings,150)['action'] is None
    r=gate.process('Fist',.80,mapping,settings,320)
    assert r['state']=='AWAITING_VERIFICATION'
    assert gate.pending_intent['pending_command']=='zoom_out'
    assert gate.process(None,0,None,settings,450)['action'] is None

def test_camera_fist_corrects_wrong_palm_classifier(monkeypatch):
    """End-to-end: a clearly curled camera fist cannot cause zoom-in."""
    from app import main
    from fastapi.testclient import TestClient
    with TestClient(main.app) as client:
        client.delete('/api/data')
        for label,pose,action in [('Open palm',0,'zoom_in'),('Fist',1,'zoom_out')]:
            resp=client.post('/api/enroll',json={
                'mapping':{'gesture_label':label,'action':action,'enabled':True,'requires_confirmation':True},
                'samples':[{'landmarks':synthetic(pose,i),'source':'camera'} for i in range(12)],
                'elapsed_seconds':1})
            assert resp.status_code==200
        client.post('/api/state',json={'state':'ARMED'})
        clock=[100.0]
        monkeypatch.setattr(main.time,'monotonic',lambda:clock[0])
        for i in range(6):
            clock[0]+=.2
            response=client.post('/api/recognize',json={'landmarks':synthetic(1,i+600),'source':'camera'})
            assert response.status_code==200
            data=response.json()
            assert data['label']=='Fist'
            assert data['action'] != 'zoom_in'
        # In two-step verification, zoom_out is requested and pending confirmation
        assert client.get('/api/status').json()['state']=='AWAITING_VERIFICATION'
        assert client.get('/api/status').json()['pending_verification']['pending_command']=='zoom_out'
        client.delete('/api/data')
