from app.safety import SafeIntent
from app.schemas import Settings

S=Settings(threshold=.10,dwell_ms=300,cooldown_ms=650)
OPEN={'enabled':True,'action':'zoom_in','threshold':None}
FIST={'enabled':True,'action':'zoom_out','threshold':None}
STOP={'enabled':True,'action':'stop_zoom','threshold':None}

CONFIRM={'enabled':True,'action':'confirm_pending','threshold':None}

def armed():
    s=SafeIntent();s.set_state('ARMED');return s

def start(gate,label,mapping):
    for t in (0,160,320):
        gate.process(label,.95,mapping,S,t,source='camera')
    assert gate.state=='AWAITING_VERIFICATION'
    for t in (400,650,950):
        gate.process('Thumbs Up',.90,CONFIRM,S,t,source='camera')
    assert gate.state=='VERIFIED'
    gate.process(label,.95,mapping,S,1050,source='camera')
    result=gate.process(label,.95,mapping,S,1200,source='camera')
    assert result['action']==mapping['action']
    assert gate.state=='ACTIVE_CONTINUOUS'

def test_hold_repeats_at_rate_limit():
    g=armed();start(g,'Palm',OPEN)
    fired=[]
    for t in (1300,1450,1600,1750,1900):
        r=g.process('Palm',.95,OPEN,S,t,source='camera')
        if r['action']:fired.append(t)
    assert fired==[1750]

def test_stop_gesture_ceases_zoom():
    g=armed();start(g,'Palm',OPEN)
    r=g.process('Peace',.95,STOP,S,1400,source='camera')
    assert r['action']=='stop_zoom'
    assert g.state=='STOPPED'
    assert g.process(None,0,None,S,1500,source='camera')['action'] is None

def test_low_confidence_or_missing_hand_never_repeat():
    g=armed();start(g,'Palm',OPEN)
    r=g.process('Palm',.05,OPEN,S,1300,source='camera')
    assert r['action'] is None
    assert r['state']=='STOPPED'
    assert g.process(None,0,None,S,1700,source='camera')['action'] is None

def test_low_threshold_does_not_arm_zoom():
    g=armed()
    for t in (0,150,350,550,750):
        assert g.process('Fist',.05,FIST,S,t)['action'] is None
