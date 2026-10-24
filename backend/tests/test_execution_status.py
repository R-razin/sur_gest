import pytest
from fastapi.testclient import TestClient
from app import main
from app.features import synthetic
from app.policy import effective_threshold
from app.schemas import Settings
from app.safety import SafeIntent
from app.classifier import PersonalizedClassifier

@pytest.fixture
def client():
    with TestClient(main.app) as c:
        c.delete('/api/data')
        yield c
        c.delete('/api/data')

def enroll(c,label='Custom fist',action='zoom_in',pose=1):
    r=c.post('/api/enroll',json={'mapping':{'gesture_label':label,'action':action,'enabled':True},'samples':[{'source':'camera','landmarks':synthetic(pose,i)} for i in range(12)],'elapsed_seconds':3})
    assert r.status_code==200
    return r.json()

def test_one_threshold_for_status_verify_and_live(client,monkeypatch):
    status=enroll(client)
    assert status['profiles'][0]['effective_threshold']==.1
    model=main.source_classifiers['camera']
    monkeypatch.setattr(model,'predict',lambda *args:('Custom fist',.05))
    v=client.post('/api/verify',json={'expected_label':'Custom fist','source':'camera','samples':[{'source':'camera','landmarks':synthetic(1,i+500)} for i in range(4)]}).json()
    assert v['threshold']==.1 and not v['passed']
    client.post('/api/state',json={'state':'ARMED'})
    r=client.post('/api/recognize',json={'source':'camera','landmarks':synthetic(1)}).json()
    assert r['effective_threshold']==.1 and r['reason_code']=='low_confidence'
    assert not r['confidence_passed'] and r['action'] is None
    assert r['mapping_status']=='enabled' and r['mapped_action']=='zoom_in'

def test_enrolled_fist_can_zoom_in_without_hardcoded_posture_veto(client,monkeypatch):
    enroll(client)
    now=[1000.];monkeypatch.setattr(main.time,'monotonic',lambda:now[0])
    client.post('/api/state',json={'state':'ARMED'})
    results=[]
    for i in range(3):
        now[0]+=.2
        results.append(client.post('/api/recognize',json={'source':'camera','landmarks':synthetic(1,500+i)}).json())
    assert results[-1]['state']=='AWAITING_VERIFICATION'
    assert results[-1]['pending_verification']['pending_command']=='zoom_in'
    client.post('/api/verification/confirm')
    results2=[]
    for i in range(3):
        now[0]+=.2
        results2.append(client.post('/api/recognize',json={'source':'camera','landmarks':synthetic(1,600+i)}).json())
    assert any(r['action']=='zoom_in' for r in results2)
    assert client.get('/api/status').json()['viewer']['zoom']==1.15

def test_discrete_actions_do_not_repeat_even_after_gap():
    gate=SafeIntent();gate.set_state('ARMED');s=Settings()
    m={'action':'next_slice','enabled':True}
    for now in [0,150,350,500]:
        r=gate.process('next',.99,m,s,now,source='camera')
    assert r['state']=='AWAITING_VERIFICATION'
    executed=[]
    for now in [600,850,1150]:
        r=gate.process('Thumbs Up',.90,{'enabled':True,'action':'confirm_pending'},s,now,source='camera')
        if r['action']: executed.append(r['action'])
    assert executed==['next_slice']
    for now in [1200,1300,1400]:
        r2=gate.process('Thumbs Up',.90,{'enabled':True,'action':'confirm_pending'},s,now,source='camera')
        assert r2['action'] is None

def test_pause_rearm_rejects_old_frames_and_motion(client):
    enroll(client)
    old=client.post('/api/state',json={'state':'ARMED'}).json()['control_revision']
    client.post('/api/state',json={'state':'PAUSED'})
    client.post('/api/state',json={'state':'ARMED'})
    r=client.post('/api/recognize',json={'source':'camera','landmarks':synthetic(1),'control_revision':old})
    assert r.status_code==409
    assert client.post('/api/motion',json={'source':'camera','action':'next_slice','control_revision':old}).status_code==409
    assert client.get('/api/status').json()['viewer']['zoom']==1

def test_verification_rejects_wrong_source_and_unstable_majority(client,monkeypatch):
    enroll(client)
    samples=[{'source':'simulation','landmarks':synthetic(1)}]*5
    assert client.post('/api/verify',json={'source':'simulation','expected_label':'Custom fist','samples':samples}).status_code==422
    predictions=iter([('Custom fist',.99)]*3+[('other',.99)]*7)
    monkeypatch.setattr(main.source_classifiers['camera'],'predict',lambda *args:next(predictions))
    samples=[{'source':'camera','landmarks':synthetic(1)}]*10
    assert not client.post('/api/verify',json={'source':'camera','expected_label':'Custom fist','samples':samples}).json()['passed']

def test_calibration_separate_by_class_and_retraining_clears_old_state():
    a=[{'label':'a','landmarks':synthetic(0,i)} for i in range(10)]
    b=[{'label':'b','landmarks':synthetic(1,i)} for i in range(10)]
    model=PersonalizedClassifier();model.train(a);radius=model.radii['a']
    model.train(a+b);assert model.radii['a']==radius and set(model.radii)=={'a','b'}
    model.train(a);assert set(model.radii)=={'a'}
    model.train([]);assert model.radii=={}

def test_per_gesture_threshold_overrides_and_zoom_floor():
    s=Settings(threshold=.1)
    assert effective_threshold({'action':'zoom_in','threshold':.2},s)==.2
    assert effective_threshold({'action':'zoom_out','threshold':.9},s)==.9
    assert effective_threshold({'action':'next_slice','threshold':.8},s)==.8
    assert effective_threshold({'action':'zoom_in','threshold':None},s)==.1

def test_camera_endpoint_to_actions_and_stop_sequence(client,monkeypatch):
    for label,pose,action in [('Open',0,'zoom_in'),('Fist',1,'zoom_out'),('Peace',3,'stop_zoom')]:enroll(client,label,action,pose)
    now=[1000.];monkeypatch.setattr(main.time,'monotonic',lambda:now[0])
    client.post('/api/state',json={'state':'ARMED'})
    for pose,expected in [(0,'zoom_in'),(1,'zoom_out'),(3,'stop_zoom')]:
        now[0]+=1
        monkeypatch.setattr(main.camera,'detect',lambda _image:synthetic(pose,600))
        for _ in range(5):
            now[0]+=.15
            points=client.post('/api/camera/landmarks',json={'image':'test-frame'}).json()['landmarks']
            client.post('/api/recognize',json={'source':'camera','landmarks':points})
        if expected != 'stop_zoom':
            # Confirm two-step verification
            client.post('/api/verification/confirm')
            post_actions=[]
            for _ in range(3):
                now[0]+=.15
                points=client.post('/api/camera/landmarks',json={'image':'test-frame'}).json()['landmarks']
                r=client.post('/api/recognize',json={'source':'camera','landmarks':points}).json()
                if r['action']: post_actions.append(r['action'])
            assert expected in post_actions
        else:
            # Stop zoom executes immediately without verification
            points=client.post('/api/camera/landmarks',json={'image':'test-frame'}).json()['landmarks']
            r=client.post('/api/recognize',json={'source':'camera','landmarks':points}).json()
            assert r['action']=='stop_zoom'
    client.post('/api/state',json={'state':'PAUSED'})
    before=client.get('/api/status').json()['viewer']
    for _ in range(10):
        now[0]+=.15
        assert client.post('/api/recognize',json={'source':'camera','landmarks':synthetic(0)}).json()['action'] is None
    assert client.get('/api/status').json()['viewer']==before

def test_health_reports_server_identity_and_current_state(client):
    h=client.get('/api/health').json()
    assert h['boot_id'] and h['state']=='IDLE'
    client.post('/api/state',json={'state':'PAUSED'})
    newer=client.get('/api/health').json()
    assert newer['boot_id']==h['boot_id'] and newer['control_revision']>h['control_revision']
