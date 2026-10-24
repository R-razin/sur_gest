from .schemas import Command, Settings
from .policy import effective_threshold


def pretty_action(action: str) -> str:
    if not action:
        return ""
    if action == "stop_zoom":
        return "Stop zoom"
    if action == "pause_control":
        return "Pause gesture control"
    if action == "confirm_pending":
        return "Confirm pending action"
    return action.replace("_", " ").capitalize()


class SafeIntent:
    """
    Two-step gesture verification state machine for safety-critical interaction.
    
    Required logical states:
      IDLE, ARMED, ACTION_CANDIDATE, AWAITING_VERIFICATION, VERIFYING,
      VERIFIED, EXECUTING, ACTIVE_CONTINUOUS, STOPPED, CANCELLED, PAUSED
    """

    VERIFICATION_TIMEOUT_MS = 5000.0   # 5-second server-side monotonic deadline
    CONFIRMATION_THRESHOLD = 0.10      # 0.10 confidence required for confirmation gesture (10%)
    CONFIRMATION_DWELL_MS = 0.0        # Fast verification: immediate (0 ms dwell required)
    CONFIRMATION_STABLE_FRAMES = 1     # Fast verification: 1 prediction required
    
    CONTINUOUS_INTERVAL_MS = 500.0     # Maximum one step every 500 ms
    CONTINUOUS_MAX_DURATION_MS = 10000.0  # Maximum session duration of 10 seconds
    CONTINUOUS_MAX_STEPS = 20          # Maximum 20 steps per confirmation
    STALE_FRAME_LIMIT_MS = 750.0       # Automatic stopping on stale frames (>750ms)

    def __init__(self):
        self.last_execution = -1e12
        self.pending_intent = None
        self.continuous_session = None
        
        # Candidate gesture tracking (for initial requested action)
        self.candidate = None
        self.started = 0.0
        self.frames = 0
        
        # Verification gesture tracking (for confirmation step)
        self.verification_candidate = None
        self.verification_started = 0.0
        self.verification_frames = 0
        
        # Continuous zoom resume tracking (for returning to original gesture in VERIFIED)
        self.resume_candidate = None
        self.resume_frames = 0
        
        self.last_frame = None
        self.state = 'IDLE'

    def reset_candidate(self):
        self.candidate = None
        self.started = 0.0
        self.frames = 0

    def executed(self):
        self.state = 'EXECUTING'

    def reset_verification(self):
        self.verification_candidate = None
        self.verification_started = 0.0
        self.verification_frames = 0

    def set_state(self, state: str):
        self.state = state
        self.reset_candidate()
        if state in ('IDLE', 'PAUSED'):
            self.pending_intent = None
            self.continuous_session = None
            self.reset_verification()
            self.resume_candidate = None
            self.resume_frames = 0
        elif state == 'ARMED':
            self.reset_verification()
            self.resume_candidate = None
            self.resume_frames = 0
        if state == 'IDLE':
            self.last_execution = -1e12
        self.last_frame = None

    def cancel_verification(self, reason: str = "Verification cancelled.") -> bool:
        """Cancel pending verification or active continuous session safely."""
        if self.state in ('AWAITING_VERIFICATION', 'VERIFYING', 'VERIFIED', 'ACTIVE_CONTINUOUS'):
            self.pending_intent = None
            self.continuous_session = None
            self.reset_verification()
            self.reset_candidate()
            self.resume_candidate = None
            self.resume_frames = 0
            self.state = 'CANCELLED'
            return True
        return False

    def request_verification(self, command: str, initiating_gesture: str, initiating_action: str,
                             source: str, now: float, verification_symbol: str = "Thumbs Up"):
        """Create a pending intent without modifying the image."""
        self.reset_candidate()
        self.reset_verification()
        self.resume_candidate = None
        self.resume_frames = 0
        self.continuous_session = None
        self.state = 'AWAITING_VERIFICATION'
        self.pending_intent = {
            'pending_command': command,
            'initiating_gesture': initiating_gesture,
            'initiating_action': initiating_action,
            'source': source,
            'deadline': now + self.VERIFICATION_TIMEOUT_MS,
            'verification_symbol': verification_symbol,
            'created_at': now
        }

    def get_pending_info(self, now: float):
        if not self.pending_intent:
            return None
        remaining_s = max(0.0, (self.pending_intent['deadline'] - now) / 1000.0)
        dwell_elapsed = max(0.0, now - self.verification_started) if self.verification_started else 0.0
        dwell_prog = min(1.0, dwell_elapsed / self.CONFIRMATION_DWELL_MS) if self.CONFIRMATION_DWELL_MS > 0 else (1.0 if self.verification_frames >= 1 else 0.0)
        return {
            'pending_command': self.pending_intent['pending_command'],
            'initiating_gesture': self.pending_intent['initiating_gesture'],
            'initiating_action': self.pending_intent['initiating_action'],
            'source': self.pending_intent['source'],
            'verification_symbol': self.pending_intent['verification_symbol'],
            'prompt': f"{pretty_action(self.pending_intent['pending_command'])} requested. Show a {self.pending_intent['verification_symbol']} to confirm.",
            'timeout_remaining_seconds': round(remaining_s, 2),
            'confidence_required': self.CONFIRMATION_THRESHOLD,
            'dwell_required_ms': int(self.CONFIRMATION_DWELL_MS),
            'dwell_progress': dwell_prog,
            'stable_frames': self.verification_frames,
            'verifying': self.state == 'VERIFYING',
            'verified': self.state in ('VERIFIED', 'ACTIVE_CONTINUOUS')
        }

    def get_continuous_info(self, now: float):
        if not self.continuous_session:
            return None
        elapsed_s = max(0.0, (now - self.continuous_session['start_time']) / 1000.0)
        return {
            'active': True,
            'command': self.continuous_session['command'],
            'initiating_gesture': self.continuous_session['initiating_gesture'],
            'step_count': self.continuous_session['step_count'],
            'max_steps': self.CONTINUOUS_MAX_STEPS,
            'session_elapsed_seconds': round(elapsed_s, 1),
            'max_session_seconds': round(self.CONTINUOUS_MAX_DURATION_MS / 1000.0, 1),
            'message': f"Continuous zoom active: {self.continuous_session['step_count']}/{self.CONTINUOUS_MAX_STEPS} steps ({round(elapsed_s, 1)}s/10s). Show Stop gesture to end."
        }

    def process(self, label, confidence, mapping, settings: Settings, now,
                source: str = 'camera', get_verification_symbol_fn=None):
        threshold = effective_threshold(mapping, settings)
        action = mapping.get('action') if mapping else None
        enabled = bool(mapping and mapping.get('enabled'))
        allowed = action in {c.value for c in Command}
        dwell = min(settings.dwell_ms, 350) if action in ('stop_zoom', 'pause_control') else settings.dwell_ms

        def result(code, reason, execute=None, latency=None):
            elapsed = max(0.0, now - self.started) if self.candidate else 0.0
            return dict(
                state=self.state,
                reason=reason,
                reason_code=code,
                action=execute,
                latency_ms=latency,
                effective_threshold=threshold,
                confidence_passed=label is not None and confidence >= threshold,
                mapping_status='missing' if not mapping else ('disabled' if not enabled else ('enabled' if allowed else 'invalid')),
                mapped_action=action,
                dwell_progress=min(1.0, elapsed / dwell, self.frames / 3) if dwell > 0 else 0.0,
                stable_frames=self.frames,
                cooldown_remaining_ms=max(0.0, settings.cooldown_ms - (now - self.last_execution)),
                pending_verification=self.get_pending_info(now),
                continuous_zoom=self.get_continuous_info(now)
            )

        # 1. IDLE or PAUSED
        if self.state in ('IDLE', 'PAUSED'):
            return result('paused' if self.state == 'PAUSED' else 'idle',
                          'Recognition is paused.' if self.state == 'PAUSED' else 'Arm the system to enable gesture commands.')

        # 2. EMERGENCY PAUSE — Works immediately!
        if action == 'pause_control' and enabled:
            self.set_state('PAUSED')
            return result('emergency_paused', 'Emergency pause triggered via recognized gesture.', 'pause_control')

        # 3. DEDICATED STOP ZOOM GESTURE — Works immediately!
        if action == 'stop_zoom' and enabled:
            if self.state == 'ACTIVE_CONTINUOUS':
                self.continuous_session = None
                self.pending_intent = None
                self.set_state('STOPPED')
                return result('zoom_stopped', 'Explicit stop gesture stopped continuous zoom.', 'stop_zoom')
            elif self.state in ('AWAITING_VERIFICATION', 'VERIFYING', 'VERIFIED'):
                self.cancel_verification('Cancelled via Stop gesture.')
                return result('verification_cancelled', 'Pending verification cancelled via Stop gesture.', 'stop_zoom')
            else:
                self.set_state('STOPPED')
                return result('stop_acknowledged', 'Stop gesture recognized.', 'stop_zoom')

        # 4. Check Stale Frames (tracking lost / elapsed > 750ms)
        if self.last_frame is not None and (now - self.last_frame) > self.STALE_FRAME_LIMIT_MS:
            if self.state == 'ACTIVE_CONTINUOUS':
                self.continuous_session = None
                self.pending_intent = None
                self.set_state('STOPPED')
                self.last_frame = now
                return result('tracking_lost_stopped', 'Continuous zoom stopped: hand tracking lost.')
            if self.state == 'ACTION_CANDIDATE':
                self.reset_candidate()
                self.set_state('ARMED')
            elif self.state == 'VERIFYING':
                self.reset_verification()
                self.set_state('AWAITING_VERIFICATION')

        self.last_frame = now

        # 5. Hand released (label is None)
        if label is None:
            if self.state == 'ACTIVE_CONTINUOUS':
                self.continuous_session = None
                self.pending_intent = None
                self.set_state('STOPPED')
                return result('tracking_lost_stopped', 'Continuous zoom stopped: hand released.')
            if self.state in ('STOPPED', 'CANCELLED', 'EXECUTING'):
                self.set_state('ARMED')
                return result('no_hand', 'Hand released. Ready for a new gesture.')
            if self.state in ('AWAITING_VERIFICATION', 'VERIFYING'):
                # Reset verification progress when hand is released during verification
                self.reset_verification()
                self.state = 'AWAITING_VERIFICATION'
                # Check deadline
                if self.pending_intent and now > self.pending_intent['deadline']:
                    self.pending_intent = None
                    self.set_state('CANCELLED')
                    return result('verification_expired', 'Verification timed out after 5.0 seconds. Action cancelled.')
                v_sym = self.pending_intent['verification_symbol'] if self.pending_intent else 'Thumbs Up'
                p_cmd = self.pending_intent['pending_command'] if self.pending_intent else 'Action'
                return result('hand_released_awaiting', f"{pretty_action(p_cmd)} requested. Show a {v_sym} to confirm.")
            if self.state == 'VERIFIED':
                p_cmd = self.pending_intent['pending_command'] if self.pending_intent else 'Zoom'
                i_gst = self.pending_intent['initiating_gesture'] if self.pending_intent else 'Open palm'
                return result('zoom_verified_awaiting', f"{pretty_action(p_cmd)} confirmed — show {i_gst} again to begin.")
            self.reset_candidate()
            self.set_state('ARMED')
            return result('no_hand', 'Hand released. Ready for a new gesture.')

        # If currently in STOPPED or CANCELLED, reset to ARMED on fresh gesture
        if self.state in ('STOPPED', 'CANCELLED', 'EXECUTING'):
            self.set_state('ARMED')

        # 6. AWAITING_VERIFICATION or VERIFYING
        if self.state in ('AWAITING_VERIFICATION', 'VERIFYING'):
            # Check Monotonic Deadline (5.0s timeout)
            if self.pending_intent and now > self.pending_intent['deadline']:
                self.pending_intent = None
                self.reset_verification()
                self.set_state('CANCELLED')
                return result('verification_expired', 'Verification timed out after 5.0 seconds. Action cancelled.')

            # Check Source Mismatch (Rule 6: Source mismatch rejected)
            if self.pending_intent and source != self.pending_intent['source']:
                return result('source_mismatch', f"Verification source mismatch: must confirm using {self.pending_intent['source']}.")

            # Check Self-Confirmation (Rule 7: Original action cannot self-confirm)
            if self.pending_intent and label.strip().lower() == self.pending_intent['initiating_gesture'].strip().lower():
                self.reset_verification()
                self.state = 'AWAITING_VERIFICATION'
                v_sym = self.pending_intent['verification_symbol']
                return result('self_confirm_rejected', f"Original gesture cannot confirm itself. Show a {v_sym} to confirm.")

            # Identify if this is the confirmation gesture
            expected_sym = self.pending_intent['verification_symbol'].strip().lower() if self.pending_intent else 'thumbs up'
            norm_label = label.strip().lower()
            is_confirmation = False
            if action == 'confirm_pending':
                is_confirmation = True
            elif norm_label in (expected_sym, 'thumbs up', 'thumbs_up', 'thumbs', 'thumb up', 'thumb_up', 'confirm'):
                is_confirmation = True
            elif 'thumb' in norm_label:
                is_confirmation = True
            elif get_verification_symbol_fn and norm_label == get_verification_symbol_fn(source).strip().lower():
                is_confirmation = True

            if not is_confirmation:
                # Rule 3: Incorrect verification rejected (do not queue or accept unrelated gesture)
                self.reset_verification()
                self.state = 'AWAITING_VERIFICATION'
                v_sym = self.pending_intent['verification_symbol'] if self.pending_intent else 'Thumbs Up'
                return result('unexpected_verification_gesture', f"Awaiting verification. Show a {v_sym} to confirm or Cancel.")

            # Rule 4: Low confidence verification rejected (Threshold: 0.10)
            if confidence < self.CONFIRMATION_THRESHOLD:
                self.reset_verification()
                self.state = 'AWAITING_VERIFICATION'
                v_sym = self.pending_intent['verification_symbol'] if self.pending_intent else 'Thumbs Up'
                return result('low_confidence_verification',
                              f"Confirmation confidence ({int(confidence*100)}%) is below required 10%. Hold {v_sym} steady.")

            # Confirmation gesture detected with confidence >= 0.10!
            self.state = 'VERIFYING'
            if self.verification_candidate != label:
                self.verification_candidate = label
                self.verification_started = now
                self.verification_frames = 1
            else:
                self.verification_frames += 1

            dwell_elapsed = now - self.verification_started
            dwell_met = dwell_elapsed >= self.CONFIRMATION_DWELL_MS
            frames_met = self.verification_frames >= self.CONFIRMATION_STABLE_FRAMES

            if not (dwell_met and frames_met):
                v_sym = self.pending_intent['verification_symbol'] if self.pending_intent else 'Thumbs Up'
                return result('verifying_progress',
                              f"Verifying confirmation: hold {v_sym} steady.")

            # CONFIRMATION SUCCESS!
            p_cmd = self.pending_intent['pending_command']
            i_gst = self.pending_intent['initiating_gesture']
            self.reset_verification()

            if p_cmd in ('zoom_in', 'zoom_out'):
                # Rule 10: Continuous zoom requires returning to original gesture
                self.state = 'VERIFIED'
                self.resume_candidate = None
                self.resume_frames = 0
                return result('zoom_confirmed_awaiting_gesture',
                              f"{pretty_action(p_cmd)} confirmed — show {i_gst} again to begin.")
            else:
                # Discrete Action: Execute authorized action exactly once!
                self.state = 'EXECUTING'
                self.last_execution = now
                self.pending_intent = None
                self.set_state('STOPPED')
                return result('action_executed', f"{pretty_action(p_cmd)} verified and executed.", p_cmd)

        # 7. VERIFIED (Only reached for continuous zoom awaiting return to initiating gesture)
        if self.state == 'VERIFIED':
            # Check deadline for resuming zoom (10s limit)
            if self.pending_intent and now > self.pending_intent['deadline'] + 10000.0:
                self.pending_intent = None
                self.set_state('CANCELLED')
                return result('zoom_activation_timeout', 'Zoom start timed out. New two-step verification required.')

            expected_initiating = self.pending_intent['initiating_gesture'].strip().lower() if self.pending_intent else ''
            p_cmd = self.pending_intent['pending_command'] if self.pending_intent else 'zoom_in'
            i_gst = self.pending_intent['initiating_gesture'] if self.pending_intent else 'Open palm'

            if label.strip().lower() != expected_initiating:
                return result('awaiting_original_gesture', f"{pretty_action(p_cmd)} confirmed — show {i_gst} again to begin.")

            if confidence < threshold:
                return result('low_confidence_resume', f"Low confidence ({int(confidence*100)}%). Hold {i_gst} steady to begin.")

            # User is holding original gesture!
            if self.resume_candidate != label:
                self.resume_candidate = label
                self.resume_frames = 1
            else:
                self.resume_frames += 1

            if self.resume_frames < 2:
                return result('validating_resume', f"Validating {i_gst} to begin zoom.")

            # Begin continuous zoom!
            self.state = 'ACTIVE_CONTINUOUS'
            self.continuous_session = {
                'command': p_cmd,
                'initiating_gesture': label,
                'start_time': now,
                'step_count': 1,
                'last_step_time': now
            }
            self.last_execution = now
            return result('continuous_started', f"Continuous zoom started: step 1/{self.CONTINUOUS_MAX_STEPS}. Show Stop gesture to end.", p_cmd)

        # 8. ACTIVE_CONTINUOUS
        if self.state == 'ACTIVE_CONTINUOUS':
            if not self.continuous_session:
                self.set_state('ARMED')
                return result('continuous_reset', 'Continuous session cleared.')

            session_cmd = self.continuous_session['command']
            initiating_gst = self.continuous_session['initiating_gesture'].strip().lower()

            # Rule 11: Stop immediately if gesture changes or tracking disappears
            if label.strip().lower() != initiating_gst:
                self.continuous_session = None
                self.pending_intent = None
                self.set_state('STOPPED')
                return result('gesture_changed_stopped', 'Continuous zoom stopped: hand posture changed.')

            if confidence < threshold:
                self.continuous_session = None
                self.pending_intent = None
                self.set_state('STOPPED')
                return result('low_confidence_stopped', f'Continuous zoom stopped: confidence {confidence:.1%} below threshold.')

            # Check 10s maximum session duration
            session_elapsed = now - self.continuous_session['start_time']
            if session_elapsed > self.CONTINUOUS_MAX_DURATION_MS:
                self.continuous_session = None
                self.pending_intent = None
                self.set_state('STOPPED')
                return result('max_duration_stopped', 'Continuous zoom stopped: 10-second session limit reached.')

            # Check 20 maximum steps per confirmation
            if self.continuous_session['step_count'] >= self.CONTINUOUS_MAX_STEPS:
                self.continuous_session = None
                self.pending_intent = None
                self.set_state('STOPPED')
                return result('max_steps_stopped', 'Continuous zoom stopped: 20-step limit reached.')

            # Stepping rate: maximum one step every 500 ms
            since_step = now - self.continuous_session['last_step_time']
            if since_step >= self.CONTINUOUS_INTERVAL_MS:
                self.continuous_session['step_count'] += 1
                self.continuous_session['last_step_time'] = now
                self.last_execution = now
                return result(
                    'continuous_step',
                    f"Continuous zoom: step {self.continuous_session['step_count']}/{self.CONTINUOUS_MAX_STEPS} ({round(session_elapsed/1000.0, 1)}s/10s). Show Stop gesture to end.",
                    session_cmd
                )
            else:
                return result('continuous_holding', 'Continuous zoom holding steady between steps.')

        # 9. ARMED or ACTION_CANDIDATE
        if not enabled or not allowed:
            self.reset_candidate()
            return result('mapping_unavailable' if not enabled else 'invalid_command',
                          'Gesture mapping is disabled or unavailable.' if not enabled else 'Rejected: command is not on allowlist.')

        if confidence < threshold:
            self.reset_candidate()
            return result('low_confidence', f'Rejected: confidence {confidence:.1%} below required {threshold:.1%} for {action}.')

        if action == 'confirm_pending':
            # Confirmation gesture without a pending action has no effect
            self.reset_candidate()
            return result('no_pending_action', 'No action is currently pending confirmation.')

        if now - self.last_execution < settings.cooldown_ms:
            self.reset_candidate()
            return result('cooldown', 'Cooldown: waiting before the next action.')

        # Candidate dwell check
        if label != self.candidate:
            self.candidate = label
            self.started = now
            self.frames = 1
        else:
            self.frames += 1

        self.state = 'ACTION_CANDIDATE'
        elapsed = now - self.started
        if elapsed < dwell or self.frames < 3:
            return result('validating', 'Validating consecutive stable frames and dwell duration.')

        # STEP 1: INITIAL GESTURE RECOGNIZED!
        # Do not modify the image — request verification symbol!
        v_symbol = get_verification_symbol_fn(source) if get_verification_symbol_fn else 'Thumbs Up'
        self.request_verification(
            command=action,
            initiating_gesture=label,
            initiating_action=action,
            source=source,
            now=now,
            verification_symbol=v_symbol
        )
        return result('verification_required', f"{pretty_action(action)} requested. Show a {v_symbol} to confirm.")
