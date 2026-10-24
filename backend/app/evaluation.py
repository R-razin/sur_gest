import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix

def metrics(truth,predictions,labels):
    if not truth: return None
    p,r,f,_=precision_recall_fscore_support(truth,predictions,labels=labels,average='macro',zero_division=0)
    return dict(accuracy=float(accuracy_score(truth,predictions)),precision=float(p),recall=float(r),f1=float(f),confusion=confusion_matrix(truth,predictions,labels=labels+['unknown']).tolist())

def event_metrics(events,duration):
    accepted=[e for e in events if e.get('action')]
    latencies=[e['latency_ms'] for e in accepted if e.get('latency_ms') is not None]
    # False activation requires explicitly labeled benchmark observations.
    labeled=[e for e in events if 'expected_action' in e]
    false=sum(bool(e.get('action')) and e['action']!=e['expected_action'] for e in labeled)
    return dict(accepted=len(accepted),rejected=sum(e.get('reason','').startswith('Rejected') for e in events),median_latency_ms=float(np.median(latencies)) if latencies else None,false_activations_per_minute=false/(duration/60) if labeled and duration>0 else None)
