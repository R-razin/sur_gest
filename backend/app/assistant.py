import re
from .schemas import Mapping

def propose(text,label):
    text=text.lower().strip()
    phrases={
        'next_slice':[r'next (?:image |image slice|slice|image)',r'forward'],
        'previous_slice':[r'previous',r'back(?:ward)?'],
        'zoom_in':[r'zoom in',r'enlarge'],
        'zoom_out':[r'zoom out',r'smaller'],
        'reset_view':[r'reset (?:view|image)',r'center (?:the )?image'],
        'pan_left':[r'(?:pan|move) left'], 'pan_right':[r'(?:pan|move) right'],
        'pan_up':[r'(?:pan|move) up'], 'pan_down':[r'(?:pan|move) down'],
        'stop_zoom':[r'stop zoom',r'stop (?:zooming|magnification)'],
        'pause_control':[r'pause(?: gesture)?(?: control)?',r'emergency stop',r'freeze (?:control|gesture)',r'halt (?:control|gesture)'],
        'confirm_pending':[r'confirm(?: pending)?',r'verification symbol',r'authorize(?: action)?',r'thumbs up']}
    actions=[action for action,patterns in phrases.items() if any(re.search(p,text) for p in patterns)]
    if len(actions)!=1 or re.search(r'\b(delete|upload|patient|operate|execute|surgery|ignore|override|bypass|disable)\b',text):
        raise ValueError('Use exactly one supported viewer action, such as “next slice” or “zoom in”.')
    
    explanations={
        'zoom_in':'Enlarges the imaging phantom slice by 15% to inspect finer structures.',
        'zoom_out':'Decreases magnification of the imaging phantom slice by 15%.',
        'next_slice':'Advances forward to the next axial phantom slice in sequence.',
        'previous_slice':'Steps backward to the preceding axial phantom slice in sequence.',
        'pan_left':'Shifts the image viewport 20 pixels to the left.',
        'pan_right':'Shifts the image viewport 20 pixels to the right.',
        'pan_up':'Shifts the image viewport 20 pixels upward.',
        'pan_down':'Shifts the image viewport 20 pixels downward.',
        'reset_view':'Restores zoom to 100% and re-centers the phantom.',
        'stop_zoom':'Stops ongoing continuous zoom while leaving recognition armed.',
        'pause_control':'Immediately halts gesture recognition, retaining manual and keyboard controls.',
        'confirm_pending':'Validates pending actions as the two-step verification confirmation symbol (e.g. Thumbs Up).'
    }
    
    return Mapping(
        gesture_label=label,
        action=actions[0],
        enabled=False,
        requires_confirmation=True,
        explanation=explanations[actions[0]]
    )
