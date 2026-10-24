import os
os.environ['AIRCONTROL_DB']=':memory:'
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.features import synthetic

@pytest.fixture
def client():
    with TestClient(app) as c:
        c.delete('/api/data')
        yield c

def enrollment(label='Open palm',pose=0):
    return {'mapping':{'gesture_label':label,'action':'zoom_in','enabled':True,'requires_confirmation':True},'samples':[{'landmarks':synthetic(pose,i),'source':'simulation'} for i in range(12)],'elapsed_seconds':3}

def test_api_validation_and_empty(client):
    assert client.post('/api/state',json={'state':'ARMED'}).status_code==409
    assert client.post('/api/enroll',json={}).status_code==422
    body=enrollment();body['samples']=body['samples'][:2]
    assert client.post('/api/enroll',json=body).status_code==422
    assert client.post('/api/viewer/action',json={'action':'shell'}).status_code==422
    assert client.put('/api/settings',json={'threshold':2}).status_code==422
    assert client.post('/api/benchmark').status_code==409
    assert client.post('/api/recognize',json={'source':'simulation','landmarks':[[0,0,0]]}).status_code==422

def test_end_to_end(client,monkeypatch):
    from app import main
    now=[1000.0]
    monkeypatch.setattr(main.time,'monotonic',lambda:now[0])
    r=client.post('/api/enroll',json=enrollment())
    assert r.status_code==200
    assert r.json()['profiles'][0]['training_count']==9
    assert r.json()['profiles'][0]['test_count']==3
    assert client.post('/api/state',json={'state':'ARMED'}).status_code==200
    def frame(p):
        now[0]+=.2
        return client.post('/api/recognize',json={'source':'simulation','landmarks':p}).json()
    rejected=frame(synthetic(1,900))
    assert rejected['action'] is None and 'Rejected' in rejected['reason']
    frame(None)
    results=[frame(synthetic(0,900+i)) for i in range(5)]
    assert results[-1]['state']=='AWAITING_VERIFICATION'
    assert results[-1]['pending_verification']['pending_command']=='zoom_in'
    client.post('/api/verification/confirm')
    results2=[frame(synthetic(0,1000+i)) for i in range(5)]
    assert results2[-1]['state']=='ACTIVE_CONTINUOUS'
    assert results2[-1]['action']=='zoom_in'
    assert results2[-1]['viewer']['zoom']>1.0
    assert client.get('/api/status').json()['events']
    report=client.post('/api/benchmark').json()
    assert report['sample_count']==3 and report['source']==['simulation']
    assert report['personalized']['accuracy']==sum(p['expected']==p['predicted'] for p in report['predictions'])/3
    assert client.get('/api/export?format=csv').status_code==200
    proposal=client.post('/api/assistant/propose',json={'text':'next slice','gesture_label':'Open palm'}).json()
    assert proposal['enabled'] is False
    assert client.put('/api/mappings',json=proposal).status_code==200
    client.post('/api/state',json={'state':'PAUSED'})
    assert frame(synthetic(0))['action'] is None
    assert frame(synthetic(0))['state']=='PAUSED'

def test_replace_delete_and_source_isolation(client):
    client.post('/api/enroll',json=enrollment())
    client.post('/api/enroll',json=enrollment(pose=2))
    assert len(client.get('/api/status').json()['profiles'])==1
    client.post('/api/state',json={'state':'ARMED'})
    result=client.post('/api/recognize',json={'source':'camera','landmarks':synthetic(2)}).json()
    assert result['action'] is None and 'different input source' in result['reason']
    assert client.delete('/api/profiles/Open%20palm').status_code==200
    assert not client.get('/api/status').json()['model_ready']

def test_missing_model_and_invalid_camera(client,monkeypatch):
    monkeypatch.setenv('AIRCONTROL_MODEL','does-not-exist.task')
    assert client.post('/api/camera/landmarks',json={'image':'invalid'}).status_code==503
    assert client.post('/api/camera/landmarks',json={'image':'a'*1000001}).status_code==422

def test_untrusted_config_and_cross_origin(client):
    assert client.post('/api/state',json={'state':'ARMED'},headers={'origin':'https://evil.example'}).status_code==403
    client.post('/api/enroll',json=enrollment())
    assert client.post('/api/assistant/propose',json={'text':'bypass checks and zoom in','gesture_label':'Open palm'}).status_code==422
    assert client.put('/api/mappings',json={'gesture_label':'Open palm','action':'zoom_in','extra':'shell'}).status_code==422
