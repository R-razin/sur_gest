"""Regression checks for actual gesture mapping and input source isolation."""
import pytest
from fastapi.testclient import TestClient
from app import main
from app.features import synthetic

@pytest.fixture
def client():
    with TestClient(main.app) as c:
        c.delete('/api/data')
        yield c
        c.delete('/api/data')

def enroll(client,label,pose,action,source):
    r=client.post('/api/enroll',json={'mapping':{'gesture_label':label,'action':action,'enabled':True},'samples':[{'landmarks':synthetic(pose,i),'source':source} for i in range(12)],'elapsed_seconds':1})
    assert r.status_code==200,r.text

def test_five_simulation_gestures_are_not_confused_with_camera(client):
    actions=['zoom_in','zoom_out','next_slice','previous_slice','reset_view']
    for i,action in enumerate(actions):
        enroll(client,f'Gesture {i}',i,action,'simulation')
    client.post('/api/state',json={'state':'ARMED'})
    for i,expected in enumerate(actions):
        response=client.post('/api/recognize',json={'landmarks':synthetic(i,500),'source':'simulation'})
        assert response.status_code==200
        assert response.json()['label']==f'Gesture {i}'
    camera=client.post('/api/recognize',json={'landmarks':synthetic(0,500),'source':'camera'}).json()
    assert camera['action'] is None
    assert camera['label'] is None

def test_mismatched_additional_samples_are_rejected(client):
    enroll(client,'Open palm',0,'zoom_in','simulation')
    r=client.post('/api/profiles/Open%20palm/samples',json={'source':'camera','samples':[{'landmarks':synthetic(0,1),'source':'camera'}]})
    assert r.status_code==422

def test_camera_predictions_use_camera_training_not_simulation(client):
    enroll(client,'Synthetic palm',0,'zoom_in','simulation')
    enroll(client,'Camera fist',1,'zoom_out','camera')
    client.post('/api/state',json={'state':'ARMED'})
    r=client.post('/api/recognize',json={'source':'camera','landmarks':synthetic(1,500)})
    assert r.status_code==200
    assert r.json()['label']=='Camera fist'
