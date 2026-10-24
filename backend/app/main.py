import json
from threading import RLock
from functools import wraps
from uuid import uuid4
import os
import time
from datetime import datetime, timezone
import numpy as np
from fastapi import FastAPI, HTTPException, Response, Request
from .schemas import (
    Settings, Mapping, Enrollment, Frame, CameraFrame, Action,
    AssistantRequest, StateRequest, Command, VerifyRequest,
    FinalizeVerificationRequest, UpdateProfileRequest, AddSamplesRequest, MotionAction
)
from .features import extract, synthetic, LandmarkSmoother
from .classifier import PersonalizedClassifier
from .safety import SafeIntent, pretty_action
from .policy import effective_threshold, ZOOM_MINIMUM
from .viewer import Viewer
from .storage import Store
from .camera import Camera
from .assistant import propose
from .evaluation import metrics, event_metrics

app=FastAPI(title='AirControl AI',version='1.0.0')
store=Store(os.getenv('AIRCONTROL_DB','aircontrol.db'))
profiles=store.get('profiles',{})
settings=Settings(**store.get('settings',{}))
events=store.get('events',[])
benchmarks=store.get('benchmarks',[])
classifier=PersonalizedClassifier()
source_classifiers = {source: PersonalizedClassifier() for source in ("simulation", "camera")}
safety=SafeIntent()
viewer=Viewer()
camera=Camera()
smoother=LandmarkSmoother()
last_source=None
control_revision=0
boot_id=str(uuid4())
control_lock=RLock()

def locked(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with control_lock:
            return fn(*args, **kwargs)
    return wrapped

def set_control_state(value):
    global control_revision
    control_revision += 1
    safety.set_state(value)
    smoother.reset()

def retrain():
    classifier.train([dict(label=label, landmarks=sample['landmarks']) for label,p in profiles.items() for sample in p['training']])
    # Camera and synthetic landmarks must never compete in the same live model.
    for source, model in source_classifiers.items():
        model.train([dict(label=label, landmarks=sample['landmarks'])
                     for label, p in profiles.items() if p['source'] == source
                     for sample in p['training']])
retrain()

@app.middleware('http')
async def local_origin(request:Request,call_next):
    # No permissive CORS. Browser mutations must originate from the local UI.
    origin=request.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:8000'):
        return Response('Origin is not permitted.',status_code=403)
    return await call_next(request)

@app.exception_handler(ValueError)
async def bad_value(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422,content={'detail':str(exc)})

def log(kind,reason,**fields):
    event=dict(id=len(events)+1,time=datetime.now(timezone.utc).isoformat(),kind=kind,reason=reason,**fields)
    events.append(event)
    del events[:-500]
    store.put('events',events)
    return event

def get_verification_symbol(source: str = 'camera') -> str:
    # 1. Profile with action confirm_pending for this source
    for label, p in profiles.items():
        if p.get('source') == source and p.get('mapping', {}).get('enabled') and p.get('mapping', {}).get('action') == 'confirm_pending':
            return label
    # 2. Any profile with thumb in label for this source
    for label, p in profiles.items():
        if p.get('source') == source and 'thumb' in label.lower():
            return label
    # 3. Default fallback
    return 'Thumbs Up'

def snapshot():
    now_ms = time.monotonic() * 1000
    pending_info = safety.get_pending_info(now_ms)
    continuous_info = safety.get_continuous_info(now_ms)
    return dict(
        control_revision=control_revision, boot_id=boot_id, zoom_minimum=ZOOM_MINIMUM,
        profiles=[
            dict(
                label=label,
                mapping=p['mapping'],
                effective_threshold=effective_threshold(p['mapping'], settings),
                training_count=len(p['training']),
                test_count=len(p['test']),
                source=p['source'],
                enrollment_seconds=p['elapsed_seconds'],
                description=p.get('description', p['mapping'].get('description', '')),
                gesture_type=p.get('gesture_type', p['mapping'].get('gesture_type', 'static')),
                accessibility_notes=p.get('accessibility_notes', p['mapping'].get('accessibility_notes', '')),
                verified=p.get('verified', p['mapping'].get('verified', True)),
                updated_at=p.get('updated_at', p.get('created_at', ''))
            )
            for label,p in profiles.items()
        ],
        settings=settings.model_dump(),
        state=safety.state,
        viewer=viewer.value,
        events=events[-100:][::-1],
        benchmarks=benchmarks,
        model_ready=classifier.model is not None,
        camera_model_available=os.path.isfile(os.getenv('AIRCONTROL_MODEL','models/hand_landmarker.task')),
        pending_verification=pending_info,
        continuous_zoom=continuous_info,
        verification_symbol=get_verification_symbol()
    )

@app.get('/api/health')
async def health():
    return dict(boot_id=boot_id, control_revision=control_revision, state=safety.state)

@app.get('/api/status')
def status(): return snapshot()

@app.get('/api/simulation/{pose}')
def simulation(pose:int,seed:int=0):
    if pose not in range(6): raise HTTPException(422,'Choose a supported synthetic pose from 0 to 5.')
    return {'landmarks':synthetic(pose,seed)}

@app.post('/api/enroll')
@locked
def enroll(body:Enrollment):
    sources={sample.source for sample in body.samples}
    if len(sources)!=1: raise ValueError('Keep camera and simulation examples in separate profiles.')
    for sample in body.samples: extract(sample.landmarks)
    label=body.mapping.gesture_label
    # Deterministic split, never feed held-out examples to fitting.
    training=[s.model_dump() for i,s in enumerate(body.samples) if i%4!=3]
    test=[s.model_dump() for i,s in enumerate(body.samples) if i%4==3]
    now_iso=datetime.now(timezone.utc).isoformat()
    profiles[label]=dict(
        mapping=body.mapping.model_dump(mode='json'),
        training=training,
        test=test,
        source=next(iter(sources)),
        elapsed_seconds=body.elapsed_seconds,
        description=body.mapping.description,
        gesture_type=body.mapping.gesture_type,
        accessibility_notes=body.mapping.accessibility_notes,
        verified=body.mapping.verified,
        created_at=now_iso,
        updated_at=now_iso
    )
    store.put('profiles',profiles)
    retrain()
    set_control_state('IDLE')
    smoother.reset()
    log('enrollment',f'Enrolled {label}: {len(training)} training and {len(test)} held-out examples.')
    return snapshot()

@app.put('/api/mappings')
@locked
def mapping(body:Mapping):
    if body.gesture_label not in profiles: raise HTTPException(404,'Enroll this gesture before saving its mapping.')
    mapping_dict=body.model_dump(mode='json')
    mapping_dict['verified']=True
    now_iso=datetime.now(timezone.utc).isoformat()
    log('configuration',f'Mapping reviewed: {body.gesture_label} → {body.action.value}.')
    profiles[body.gesture_label]['mapping']=mapping_dict
    profiles[body.gesture_label]['verified']=True
    profiles[body.gesture_label]['updated_at']=now_iso
    store.put('profiles',profiles)
    set_control_state('IDLE')
    smoother.reset()
    return snapshot()

@app.put('/api/profiles/{label}')
@locked
def update_profile(label:str,body:UpdateProfileRequest):
    if label not in profiles: raise HTTPException(404,'Profile not found.')
    profile=profiles[label]
    target_label=body.new_label or label
    now_iso=datetime.now(timezone.utc).isoformat()
    if target_label!=label:
        if target_label in profiles: raise HTTPException(409,f"A gesture named '{target_label}' already exists.")
        del profiles[label]
        profile['mapping']['gesture_label']=target_label
        label=target_label
    if body.description is not None:
        profile['description']=body.description
        profile['mapping']['description']=body.description
    if body.accessibility_notes is not None:
        profile['accessibility_notes']=body.accessibility_notes
        profile['mapping']['accessibility_notes']=body.accessibility_notes
    if body.gesture_type is not None:
        profile['gesture_type']=body.gesture_type
        profile['mapping']['gesture_type']=body.gesture_type
    if body.action is not None:
        profile['mapping']['action']=body.action.value
    if body.threshold is not None:
        profile['mapping']['threshold']=body.threshold
    if body.enabled is not None:
        profile['mapping']['enabled']=body.enabled
    profile['verified']=True
    profile['mapping']['verified']=True
    profile['updated_at']=now_iso
    profiles[label]=profile
    store.put('profiles',profiles)
    retrain()
    set_control_state('IDLE')
    smoother.reset()
    return snapshot()

@app.post('/api/profiles/{label}/samples')
@locked
def add_samples(label:str,body:AddSamplesRequest):
    if label not in profiles: raise HTTPException(404,'Profile not found.')
    for s in body.samples: extract(s.landmarks)
    profile=profiles[label]
    if body.source != profile['source'] or any(s.source != profile['source'] for s in body.samples):
        raise HTTPException(422, 'Additional samples must use the same input source as the enrolled profile.')
    if any(sample.source != profile['source'] for sample in body.samples):
        raise ValueError('Additional samples must match this profile input source.')
    now_iso=datetime.now(timezone.utc).isoformat()
    new_train=[s.model_dump() for i,s in enumerate(body.samples) if i%4!=3]
    new_test=[s.model_dump() for i,s in enumerate(body.samples) if i%4==3]
    profile['training'].extend(new_train)
    profile['test'].extend(new_test)
    profile['verified']=True
    profile['mapping']['verified']=True
    profile['updated_at']=now_iso
    store.put('profiles',profiles)
    retrain()
    set_control_state('IDLE')
    smoother.reset()
    log('enrollment',f"Added {len(new_train)} training and {len(new_test)} test samples to '{label}'.")
    return snapshot()

@app.post('/api/verify')
@locked
def verify(body:VerifyRequest):
    if classifier.model is None: raise HTTPException(409,'Train the model before running verification.')
    if body.expected_label not in profiles: raise HTTPException(404,f"Gesture '{body.expected_label}' is not enrolled.")
    profile=profiles[body.expected_label]
    threshold=effective_threshold(profile['mapping'], settings)
    if body.source != profile['source'] or any(s.source != body.source for s in body.samples):
        raise HTTPException(422, 'Verification samples must match the enrolled input source.')
    model=source_classifiers[body.source]
    frame_preds=[]
    for s in body.samples:
        try:
            pred_label,conf=model.predict(s.landmarks,settings.sensitivity)
            frame_preds.append((pred_label,conf))
        except Exception:
            continue
    if not frame_preds:
        return {'passed':False,'expected_label':body.expected_label,'predicted_label':None,'confidence':0.,'threshold':threshold,'match':False,'stable':False,'reason':'No valid hand landmark frames could be extracted from sample.','details':[]}
    from collections import Counter
    counts=Counter(p[0] for p in frame_preds)
    majority_label,count=counts.most_common(1)[0]
    avg_conf=float(np.mean([c for l,c in frame_preds if l==majority_label]))
    match=(majority_label==body.expected_label)
    stable=(len(frame_preds)>=3 and count/len(frame_preds)>=0.8)
    conf_ok=(avg_conf>=threshold and sum(l==body.expected_label and c>=threshold for l,c in frame_preds)/len(frame_preds)>=0.8)
    passed=bool(match and stable and conf_ok)
    if passed:
        reason=f"The system recognized your gesture as '{majority_label}' with {int(avg_conf*100)}% confidence ({count}/{len(frame_preds)} frames stable)."
    elif not match:
        reason=f"The system predicted '{majority_label}' instead of '{body.expected_label}'. Please retry or add more distinctive training samples."
    elif not conf_ok:
        reason=f"Recognition confidence ({int(avg_conf*100)}%) is below the required threshold ({int(threshold*100)}%)."
    else:
        reason="The gesture was unstable across frames. Hold the pose steady during capture."
    log('verification',reason,expected=body.expected_label,predicted=majority_label,confidence=round(avg_conf,3),passed=passed)
    return {'passed':passed,'expected_label':body.expected_label,'predicted_label':majority_label,'confidence':round(avg_conf,4),'threshold':threshold,'match':match,'stable':stable,'reason':reason,'details':[{'label':l,'confidence':round(c,3)} for l,c in frame_preds]}

@app.post('/api/lab/finalize')
@locked
def finalize_verification(body:FinalizeVerificationRequest):
    if body.gesture_label not in profiles: raise HTTPException(404,f"Gesture '{body.gesture_label}' is not enrolled.")
    profile=profiles[body.gesture_label]
    now_iso=datetime.now(timezone.utc).isoformat()
    profile['verified']=True
    profile['mapping']['verified']=True
    profile['mapping']['enabled']=bool(body.enabled)
    profile['updated_at']=now_iso
    store.put('profiles',profiles)
    log('gesture',f"Gesture '{body.gesture_label}' saved: active={profile['mapping']['enabled']}.")
    return snapshot()

@app.delete('/api/profiles/{label}')
@locked
def delete_profile(label:str):
    if label not in profiles: raise HTTPException(404,'Profile not found.')
    del profiles[label]
    store.put('profiles',profiles)
    retrain()
    set_control_state('IDLE')
    smoother.reset()
    return snapshot()

@app.put('/api/settings')
@locked
def configure(body:Settings):
    global settings
    settings=body
    store.put('settings',body.model_dump())
    set_control_state('IDLE')
    smoother.reset()
    return snapshot()

@app.post('/api/state')
@locked
def state(body:StateRequest):
    if body.state=='ARMED' and not any(p['mapping']['enabled'] for p in profiles.values()):
        raise HTTPException(409,'Enroll and enable at least one gesture mapping first.')
    set_control_state(body.state)
    smoother.reset()
    log('state',f'System {body.state.lower()}.')
    return snapshot()

@app.post('/api/recognize')
@locked
def recognize(body:Frame):
    global last_source
    if body.control_revision is not None and body.control_revision != control_revision:
        raise HTTPException(409, 'Control state changed. Discard the stale frame and activate again.')
    start=time.perf_counter()
    if last_source!=body.source:
        smoother.reset()
        safety.candidate=None
        safety.frames=0
        safety.latched=False
        safety.latched_label=None
        safety.zoom_stable_frames=0
        last_source=body.source
    label=None
    confidence=0.
    mapping=None
    if body.landmarks is not None:
        extract(body.landmarks)  # Validate even when no model has been enrolled.
        model=source_classifiers[body.source]
        if model.model is None:
            # Do not classify camera input using training poses from simulation.
            result=safety.process(None, 0., None, settings, time.monotonic()*1000)
            result.update(control_revision=control_revision,reason_code='source_unavailable',reason=f'Gesture was trained for a different input source, or no {body.source} profile exists. Enroll in {body.source.capitalize()} mode.',
                          label=None, confidence=0., source=body.source,
                          processing_ms=round((time.perf_counter()-start)*1000,2),viewer=viewer.value)
            return result
        points=smoother.apply(body.landmarks,settings.smoothing)
        label,confidence=model.predict(points,settings.sensitivity)
        profile=profiles[label]
        mapping=profile['mapping']
    else:
        smoother.reset()
    now_ms=time.monotonic()*1000
    result=safety.process(label,confidence,mapping,settings,now_ms,source=body.source,get_verification_symbol_fn=get_verification_symbol)
    if result.get('action'):
        act=result['action']
        if act=='stop_zoom':
            safety.set_state('STOPPED')
            log('safety','Explicit stop gesture stopped continuous zoom.',action=act)
        elif act=='pause_control':
            set_control_state('PAUSED')
            log('safety','Emergency pause triggered via recognized gesture.',action=act)
        else:
            viewer.execute(act)
            log('execution',f"Executed {pretty_action(act)} after two-step verification.",action=act)
        result['state']=safety.state
        result['transitions']=['CANDIDATE','AWAITING_VERIFICATION','VERIFYING','VERIFIED','PAUSED' if act=='pause_control' else ('STOPPED' if act=='stop_zoom' else 'EXECUTED')]
    result.update(control_revision=control_revision,label=label,confidence=confidence,source=body.source,processing_ms=round((time.perf_counter()-start)*1000,2),viewer=viewer.value)
    # Persist state changes, executions and rejects; avoid logging every stable frame.
    if not events or events[-1]['reason']!=result['reason'] or result.get('action'):
        log('recognition',**{k:v for k,v in result.items() if k!='viewer'})
    return result

@app.post('/api/camera/landmarks')
def camera_landmarks(body:CameraFrame):
    try: return {'landmarks':camera.detect(body.image)}
    except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc


# Dynamic swipe commands are accepted only while armed, from a live camera,
# and are rate-limited separately from static-pose commands.
last_motion_execution = -1e12

@app.post('/api/motion')
@locked
def motion(body: MotionAction):
    global last_motion_execution
    if body.control_revision is not None and body.control_revision != control_revision:
        raise HTTPException(409, 'Control state changed. Discard stale motion input.')
    if safety.state != 'ARMED':
        raise HTTPException(409, f'Cannot swipe: system state is {safety.state}. Activate gesture control first.')
    now = time.monotonic() * 1000
    if now - last_motion_execution < max(650, settings.cooldown_ms):
        raise HTTPException(429, 'Swipe cooldown: move your hand back to rest.')
    # Cancel static-pose candidate and reset its dwell timing.
    safety.candidate = None
    safety.frames = 0
    last_motion_execution = now

    # Rule 9: Swipe requires two-step verification!
    v_symbol = get_verification_symbol(body.source)
    safety.request_verification(
        command=body.action,
        initiating_gesture='Swipe ' + ('right' if body.action == 'next_slice' else 'left'),
        initiating_action=body.action,
        source=body.source,
        now=now,
        verification_symbol=v_symbol
    )
    log('motion', f"{pretty_action(body.action)} requested via swipe. Show a {v_symbol} to confirm.", action=body.action, source=body.source)
    return snapshot()

@app.post('/api/verification/cancel')
@locked
def cancel_verification():
    cancelled = safety.cancel_verification('User cancelled pending verification.')
    if cancelled:
        log('safety', 'Pending verification cancelled by user.')
    return snapshot()

@app.post('/api/verification/confirm')
@locked
def confirm_verification():
    if safety.pending_intent:
        cmd = safety.pending_intent['pending_command']
        if cmd in ('zoom_in', 'zoom_out'):
            safety.state = 'VERIFIED'
            log('safety', f"Pending {cmd} verified via explicit confirmation.")
        else:
            viewer.execute(cmd)
            safety.state = 'EXECUTING'
            safety.last_execution = time.monotonic() * 1000
            safety.pending_intent = None
            safety.set_state('ARMED')
            log('execution', f"Executed {cmd} via explicit confirmation.", action=cmd)
    return snapshot()

@app.post('/api/viewer/series/{series_index}')
@locked
def select_series(series_index: int):
    if series_index not in range(4):
        raise HTTPException(422, 'Choose a synthetic series from 0 to 3.')
    # Series selection is an explicit manual fallback.
    viewer.history.append(viewer.value.copy())
    viewer.history = viewer.history[-100:]
    viewer.value['slice'] = series_index * 32 + 16
    log('manual', 'Selected a synthetic image series.', series=series_index)
    return snapshot()

@app.post('/api/viewer/action')
@locked
def manual(body:Action):
    viewer.execute(body.action)
    log('manual','Manual fallback action.',action=body.action.value)
    return snapshot()

@app.post('/api/viewer/undo')
@locked
def undo():
    viewer.undo()
    log('manual','Undid last viewer action.')
    return snapshot()

@app.post('/api/assistant/propose')
def assistant(body:AssistantRequest):
    if body.gesture_label not in profiles: raise HTTPException(409,'Select an enrolled gesture first.')
    return propose(body.text,body.gesture_label)

@app.post('/api/benchmark')
def benchmark():
    rows=[(label,sample) for label,p in profiles.items() for sample in p['test']]
    if not rows: raise HTTPException(409,'Enroll a gesture to create held-out evaluation examples first.')
    labels=sorted(profiles)
    truth=[]
    predicted=[]
    baseline=[]
    baseline_truth=[]
    predicted_actions=[]
    observations=[]
    clock=0
    gate=SafeIntent()
    gate.set_state('ARMED')
    fixed_actions=['zoom_in','zoom_out','next_slice','previous_slice','reset_view']
    templates=np.array([extract(synthetic(i,10000)) for i in range(5)])
    for label,sample in rows:
        prediction,confidence=source_classifiers[sample['source']].predict(sample['landmarks'],settings.sensitivity)
        p=profiles[prediction]
        threshold=effective_threshold(p['mapping'], settings)
        predicted.append(prediction if confidence>=threshold else 'unknown')
        predicted_actions.append(p['mapping']['action'] if confidence>=threshold else 'unknown')
        truth.append(label)
        nearest=int(np.argmin(np.linalg.norm(templates-extract(sample['landmarks']),axis=1)))
        baseline.append(fixed_actions[nearest])
        baseline_truth.append(profiles[label]['mapping']['action'])
        expected=profiles[label]['mapping']['action'] if profiles[label]['mapping']['enabled'] else None
        clock+=settings.cooldown_ms+200
        gate.process(None,0,None,settings,clock)
        for _ in range(int(settings.dwell_ms/100)+3):
            clock+=100
            r=gate.process(prediction,confidence,p['mapping'],settings,clock)
            observations.append(dict(**r,expected_action=expected))
            if r['action']: gate.executed()
    # A defined idle interval with no hand checks unintended execution.
    for _ in range(20):
        clock+=100
        observations.append(dict(**gate.process(None,0,None,settings,clock),expected_action=None))
    command_labels=sorted(set(baseline_truth))
    report=dict(id=len(benchmarks)+1,time=datetime.now(timezone.utc).isoformat(),source=sorted({s['source'] for _,s in rows}),sample_count=len(rows),duration_seconds=clock/1000,duration_kind='Deterministic replay timeline (not wall-clock or clinical testing)',labels=labels,personalized=metrics(baseline_truth,predicted_actions,command_labels),gesture_metrics=metrics(truth,predicted,labels),baseline=metrics(baseline_truth,baseline,command_labels),events=event_metrics(observations,clock/1000),enrollment_seconds=sum(p['elapsed_seconds'] for p in profiles.values()),predictions=[dict(expected=t,predicted=p) for t,p in zip(truth,predicted)],limitations=['Small sample size; collect independent sessions for reliable estimates.','Held-out frames from an enrollment session are correlated.','Synthetic fixed-pose baseline is not a validated human baseline.','False activations use labeled replay intervals, not a real-world rate.','Horizontal swipes are handled by a separate heuristic; arbitrary dynamic gestures are not trained.'])
    benchmarks.append(report)
    del benchmarks[:-20]
    store.put('benchmarks',benchmarks)
    return report

@app.get('/api/export')
def export(format:str='json'):
    if format=='json': return Response(json.dumps(dict(benchmarks=benchmarks,events=events),indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename=aircontrol-results.json'})
    if format!='csv': raise HTTPException(422,'Use json or csv.')
    import csv,io
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(['session','sources','test_examples','replay_seconds','accuracy','precision','recall','f1','baseline_accuracy','accepted','rejected','median_latency_ms','false_activations_per_minute'])
    for b in benchmarks:
        writer.writerow([b['id'],'+'.join(b['source']),b['sample_count'],b['duration_seconds'],*[b['personalized'][k] for k in ['accuracy','precision','recall','f1']],b['baseline']['accuracy'],*[b['events'][k] for k in ['accepted','rejected','median_latency_ms','false_activations_per_minute']]])
    return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=aircontrol-results.csv'})

@app.delete('/api/data')
@locked
def clear_data():
    global settings, last_motion_execution
    profiles.clear(); events.clear(); benchmarks.clear()
    store.clear()
    settings=Settings()
    last_motion_execution = -1e12
    retrain(); smoother.reset(); set_control_state('IDLE')
    viewer.__init__()
    return snapshot()
