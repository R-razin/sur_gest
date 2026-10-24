import os
os.environ['AIRCONTROL_DB']=':memory:'
from fastapi.testclient import TestClient
from app.main import app
from app.features import synthetic

def test_swipe_routes_and_series_selection():
    with TestClient(app) as c:
        c.delete('/api/data')
        assert c.post('/api/motion',json={'action':'next_slice','source':'camera'}).status_code==409
        assert c.post('/api/motion',json={'action':'zoom_in','source':'camera'}).status_code==422
        assert c.post('/api/motion',json={'action':'next_slice','source':'simulation'}).status_code==422
        assert c.post('/api/viewer/series/4').status_code==422
        data=c.post('/api/viewer/series/3').json()
        assert data['viewer']['slice']==112
        samples=[{'landmarks':synthetic(0,i),'source':'simulation'} for i in range(12)]
        payload={'mapping':{'gesture_label':'Palm','action':'zoom_in','enabled':True},'samples':samples,'elapsed_seconds':3}
        assert c.post('/api/enroll',json=payload).status_code==200
        assert c.post('/api/state',json={'state':'ARMED'}).status_code==200
        r=c.post('/api/motion',json={'action':'next_slice','source':'camera'})
        assert r.status_code==200
        assert r.json()['state']=='AWAITING_VERIFICATION'
        assert r.json()['viewer']['slice']==112
        # After explicit confirmation, action executes
        c_conf=c.post('/api/verification/confirm')
        assert c_conf.json()['viewer']['slice']==113
        assert c.post('/api/motion',json={'action':'next_slice','source':'camera'}).status_code==429
        assert c.post('/api/state',json={'state':'PAUSED'}).status_code==200
        assert c.post('/api/motion',json={'action':'previous_slice','source':'camera'}).status_code==409
