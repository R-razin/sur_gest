from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Command(str, Enum):
    zoom_in='zoom_in'
    zoom_out='zoom_out'
    next_slice='next_slice'
    previous_slice='previous_slice'
    pan_left='pan_left'
    pan_right='pan_right'
    pan_up='pan_up'
    pan_down='pan_down'
    reset_view='reset_view'
    pause_control='pause_control'
    stop_zoom='stop_zoom'
    confirm_pending='confirm_pending'

class Settings(Strict):
    threshold: float = Field(default=.10, ge=.10, le=1)
    smoothing: float = Field(default=.20, ge=0, le=.9)
    dwell_ms: int = Field(default=300, ge=100, le=3000)
    cooldown_ms: int = Field(default=650, ge=100, le=5000)
    sensitivity: float = Field(default=1.35, ge=.5, le=2)

class Mapping(Strict):
    gesture_label: str = Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9 _-]+$')
    action: Command
    requires_confirmation: Literal[True] = True
    enabled: bool = False
    threshold: float | None = Field(default=None,ge=.10,le=1)
    description: str = Field(default='', max_length=200)
    gesture_type: Literal['static', 'dynamic'] = Field(default='static')
    accessibility_notes: str = Field(default='', max_length=200)
    verified: bool = Field(default=True)
    explanation: str = Field(default='', max_length=500)

class Sample(Strict):
    landmarks: list[list[float]] = Field(min_length=21,max_length=21)
    source: Literal['simulation','camera']

class Enrollment(Strict):
    mapping: Mapping
    samples: list[Sample] = Field(min_length=8,max_length=100)
    elapsed_seconds: float = Field(ge=0,le=86400)

class VerifyRequest(Strict):
    expected_label: str = Field(min_length=1, max_length=40)
    samples: list[Sample] = Field(min_length=1, max_length=100)
    source: Literal['simulation', 'camera'] = 'simulation'

class FinalizeVerificationRequest(Strict):
    gesture_label: str = Field(min_length=1, max_length=40)
    verified: bool = True
    enabled: bool = False
    stage1_passed: bool
    user_confirmed1: bool
    stage2_passed: bool
    user_confirmed2: bool

class UpdateProfileRequest(Strict):
    new_label: str | None = Field(default=None, min_length=1, max_length=40, pattern=r'^[A-Za-z0-9 _-]+$')
    description: str | None = Field(default=None, max_length=200)
    accessibility_notes: str | None = Field(default=None, max_length=200)
    gesture_type: Literal['static', 'dynamic'] | None = None
    action: Command | None = None
    enabled: bool | None = None
    threshold: float | None = Field(default=None, ge=.10, le=1)

class AddSamplesRequest(Strict):
    samples: list[Sample] = Field(min_length=1, max_length=100)
    source: Literal['simulation', 'camera'] = 'simulation'

class Frame(Strict):
    landmarks: list[list[float]] | None = None
    source: Literal['simulation','camera']
    control_revision: int | None = Field(default=None, ge=0)

class CameraFrame(Strict):
    image: str = Field(max_length=1000000)

class Action(Strict):
    action: Command

class AssistantRequest(Strict):
    text: str = Field(min_length=1,max_length=500)
    gesture_label: str

class StateRequest(Strict):
    state: Literal['ARMED','PAUSED','IDLE']

class MotionAction(Strict):
    action: Literal['next_slice', 'previous_slice']
    source: Literal['camera']
    control_revision: int | None = Field(default=None, ge=0)
