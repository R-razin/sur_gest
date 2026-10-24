from .schemas import Command

class Viewer:
    def __init__(self):
        self.value={'slice':63,'zoom':1.,'x':0,'y':0}
        self.history=[]

    def execute(self,command):
        action=Command(command).value
        self.history.append(self.value.copy())
        self.history=self.history[-100:]
        v=self.value
        if action=='zoom_in': v['zoom']=min(4,round(v['zoom']+.15,2))
        elif action=='zoom_out': v['zoom']=max(.5,round(v['zoom']-.15,2))
        elif action=='next_slice': v['slice']=min(127,v['slice']+1)
        elif action=='previous_slice': v['slice']=max(0,v['slice']-1)
        elif action=='pan_left': v['x']=max(-200,v['x']-20)
        elif action=='pan_right': v['x']=min(200,v['x']+20)
        elif action=='pan_up': v['y']=max(-200,v['y']-20)
        elif action=='pan_down': v['y']=min(200,v['y']+20)
        elif action=='reset_view': self.value={'slice':63,'zoom':1.,'x':0,'y':0}
        elif action in ('pause_control','stop_zoom','confirm_pending'): pass
        return self.value

    def undo(self):
        if self.history: self.value=self.history.pop()
        return self.value
