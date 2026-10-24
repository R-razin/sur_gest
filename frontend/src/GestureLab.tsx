import {useState,useRef,useEffect} from 'react';
import {
  Hand,Check,X,RotateCcw,Video,
  Layers,Sparkles,AlertTriangle,Play,CheckCircle2,
  Trash2,Edit3,Plus,PlusCircle,Camera,ShieldCheck,ShieldAlert
} from 'lucide-react';
import {api} from './api';
import {commands,pretty,type Status,type Command,type Profile,type Mapping} from './types';

interface GestureLabProps {
  status: Status;
  mode: 'simulation' | 'camera';
  pose: number;
  poseNames: string[];
  cameraActive: boolean;
  cameraStream?: MediaStream | null;
  onRefresh: () => Promise<Status>;
  onEnableCamera: () => Promise<void>;
  onHalt: () => void;
  getPoints: (forEnrollment?: boolean) => Promise<number[][] | null>;
  onNavigate: (pageIndex: number) => void;
  setNotice: (msg: string) => void;
  setError: (msg: string) => void;
}

export function GestureLab({
  status,
  mode,
  pose,
  poseNames,
  cameraActive,
  cameraStream,
  onRefresh,
  onEnableCamera,
  onHalt,
  getPoints,
  onNavigate,
  setNotice,
  setError
}: GestureLabProps) {
  const cameraVideoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const element = cameraVideoRef.current;
    if (!element) return;
    if (!cameraStream || !cameraActive) {
      element.srcObject = null;
      return;
    }
    element.srcObject = cameraStream;
    void element.play().catch(() => {
      setError('Camera preview could not start. Check browser camera permission and retry.');
    });
  }, [cameraStream, cameraActive, setError]);

  const mounted=useRef(true), captureEpoch=useRef(0), countdownTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const getPointsRef=useRef(getPoints);getPointsRef.current=getPoints;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;captureEpoch.current++;cancelRecordingRef.current=true;if(countdownTimer.current)clearTimeout(countdownTimer.current);};},[]);

  // Navigation inside Lab
  const [activeTab, setActiveTab] = useState<'wizard' | 'management'>('wizard');

  const confirmationProfile = status.profiles.find(p => p.source === mode && p.mapping.enabled && (p.mapping.action === 'confirm_pending' || p.label.toLowerCase().includes('thumb')));

  const quickEnrollThumbsUp = () => {
    setActiveTab('wizard');
    setStep(2);
    setGestureName('Thumbs Up');
    setDescription('Two-step verification confirmation symbol.');
    setAccessibilityNotes('Hold hand up with thumb extended.');
    setGestureType('static');
    setSelectedAction('confirm_pending');
  };

  // Wizard Step: 1: Capture, 2: Label, 3: Action, 4: Train & Activate
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Step 1: Capture
  const [durationSec, setDurationSec] = useState<number>(3);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [capturedSamples, setCapturedSamples] = useState<{landmarks: number[][]; source: 'simulation' | 'camera'}[]>([]);
  const [currentLiveLandmarks, setCurrentLiveLandmarks] = useState<number[][] | null>(null);
  const [trackingQuality, setTrackingQuality] = useState<{status: 'good' | 'missing' | 'small' | 'edge'; message: string}>({
    status: 'good',
    message: 'Hand tracking is stable'
  });
  const cancelRecordingRef = useRef<boolean>(false);

  useEffect(()=>{
    captureEpoch.current++;cancelRecordingRef.current=true;
    if(countdownTimer.current)clearTimeout(countdownTimer.current);
    setCountdown(null);setIsRecording(false);setCapturedSamples([]);setStep(1);
    
    setAddingSamplesTo(null);setIsRecordingAdditional(false);setAddSamplesCountdown(null);
  },[mode]);

  // Step 2: Name & Label
  const [gestureName, setGestureName] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [gestureType, setGestureType] = useState<'static' | 'dynamic'>('static');
  const [accessibilityNotes, setAccessibilityNotes] = useState<string>('');

  // Step 3: Action Mapping
  const [selectedAction, setSelectedAction] = useState<Command>('zoom_in');
  const [naturalDesc, setNaturalDesc] = useState<string>('When I perform this gesture, enlarge the phantom slice.');
  const [assistantProposal, setAssistantProposal] = useState<Mapping | null>(null);
  const [isProposing, setIsProposing] = useState<boolean>(false);

  // Step 4: Training & Direct Activation
  const [isTraining, setIsTraining] = useState<boolean>(false);
  const [trainingDone, setTrainingDone] = useState<boolean>(false);
  const [trainingDurationMs, setTrainingDurationMs] = useState<number>(0);

  // Management tab states
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);
  const [editAction, setEditAction] = useState<Command>('zoom_in');
  const [editDescription, setEditDescription] = useState<string>('');
  const [editAccessibility, setEditAccessibility] = useState<string>('');
  const [addingSamplesTo, setAddingSamplesTo] = useState<string | null>(null);
  const [addSamplesCountdown, setAddSamplesCountdown] = useState<number | null>(null);
  const [isRecordingAdditional, setIsRecordingAdditional] = useState<boolean>(false);

  // Advisor / Suggestions
  const [dismissedSuggestions, setDismissedSuggestions] = useState<string[]>([]);

  // Quality check on incoming landmarks
  const checkHandQuality = (pts: number[][] | null) => {
    if (!pts || pts.length !== 21) {
      return {status: 'missing' as const, message: 'No hand detected in view'};
    }
    const outOfBounds = pts.some(p => p[0] < 0.02 || p[0] > 0.98 || p[1] < 0.02 || p[1] > 0.98);
    if (outOfBounds) {
      return {status: 'edge' as const, message: 'Hand is partially near frame boundary'};
    }
    const dx = pts[9][0] - pts[0][0];
    const dy = pts[9][1] - pts[0][1];
    const dz = pts[9][2] - pts[0][2];
    const scale = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (scale < 0.04) {
      return {status: 'small' as const, message: 'Hand is too far or small'};
    }
    return {status: 'good' as const, message: 'Hand tracking is stable and well-framed'};
  };

  // Preview awaits each frame. Recording/verification own the same capture
  // coordinator while active, so there is never a second inference stream.
  useEffect(() => {
    if ((step !== 1 || activeTab !== 'wizard') && !addingSamplesTo) return;
    if(isRecording||isRecordingAdditional||countdown!==null)return;
    let active=true;let timer:ReturnType<typeof setTimeout>;
    async function preview(){
      try{const pts=await getPointsRef.current(true);if(active){setCurrentLiveLandmarks(pts);setTrackingQuality(checkHandQuality(pts));}}
      catch{/* Permission/model errors are surfaced by explicit capture. */}
      finally{if(active)timer=setTimeout(preview,150);}
    }
    void preview();return()=>{active=false;clearTimeout(timer);};
  }, [step,activeTab,isRecording,isRecordingAdditional,addingSamplesTo,countdown,mode]);

  const runCountdown = (onDone: () => void) => {
    const epoch=++captureEpoch.current;let left=3;
    const advance=()=>{
      if(!mounted.current||epoch!==captureEpoch.current)return;
      if(left===0){setCountdown(null);onDone();return;}
      setCountdown(left--);countdownTimer.current=setTimeout(advance,700);
    };
    advance();
  };

  // Step 1: Start Recording
  const startRecording = () => {
    cancelRecordingRef.current = false;
    runCountdown(async () => {
      setIsRecording(true);
      const framesToCapture = Math.round(durationSec * 5);
      const batch: typeof capturedSamples = [];
      try {
        for (let i = 0; i < framesToCapture; i++) {
          if (cancelRecordingRef.current) break;
          const pts = await getPointsRef.current(true);
          if(!mounted.current||cancelRecordingRef.current)break;
          if (pts) {
            batch.push({landmarks: pts, source: mode});
            setCurrentLiveLandmarks(pts);
          }
          await new Promise(r => setTimeout(r, 180));
        }
        if(!mounted.current||cancelRecordingRef.current)return;
        if (batch.length < 8) {
          setError(`Only captured ${batch.length} valid frames. Please keep your hand clearly visible and retry.`);
        } else {
          setCapturedSamples(prev => [...prev, ...batch]);
          setNotice(`Captured ${batch.length} samples. Total recorded: ${capturedSamples.length + batch.length}.`);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error capturing gesture frames.');
      } finally {
        setIsRecording(false);
      }
    });
  };

  const stopRecording = () => {
    cancelRecordingRef.current = true;captureEpoch.current++;if(countdownTimer.current)clearTimeout(countdownTimer.current);
    setIsRecording(false);
    setCountdown(null);
  };

  // Step 3: Ask Assistant
  const interpretWithAssistant = async () => {
    setIsProposing(true);
    setAssistantProposal(null);
    try {
      const tempLabel = gestureName.trim() || 'Custom Gesture';
      const res = await api<Mapping>('/assistant/propose', 'POST', {
        text: naturalDesc,
        gesture_label: status.profiles[0]?.label || 'Open palm'
      });
      res.gesture_label = tempLabel;
      setAssistantProposal(res);
      setSelectedAction(res.action);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not interpret natural language description.');
    } finally {
      setIsProposing(false);
    }
  };

  // Step 4: Train & Activate Gesture Directly
  const trainAndSaveGesture = async (activateImmediately: boolean) => {
    setIsTraining(true);
    const start = performance.now();
    try {
      const payload = {
        mapping: {
          gesture_label: gestureName.trim(),
          action: selectedAction,
          enabled: activateImmediately,
          requires_confirmation: true,
          threshold: null,
          description: description.trim(),
          gesture_type: gestureType,
          accessibility_notes: accessibilityNotes.trim(),
          verified: true
        },
        samples: capturedSamples,
        elapsed_seconds: (performance.now() - start) / 1000
      };
      await api<Status>('/enroll', 'POST', payload);
      await onRefresh();
      setTrainingDurationMs(Math.round(performance.now() - start));
      setTrainingDone(true);
      setNotice(
        activateImmediately
          ? `Gesture '${gestureName.trim()}' trained and activated successfully!`
          : `Gesture '${gestureName.trim()}' trained and saved on standby.`
      );
      resetWizard();
      setActiveTab('management');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to train and save gesture.');
    } finally {
      setIsTraining(false);
    }
  };

  const resetWizard = () => {
    setStep(1);
    setCapturedSamples([]);
    setGestureName('');
    setDescription('');
    setAccessibilityNotes('');
    setGestureType('static');
    setSelectedAction('zoom_in');
    setAssistantProposal(null);
    setTrainingDone(false);
  };

  // Management: Toggle profile active/inactive directly
  const toggleProfileActive = async (profile: Profile) => {
    try {
      onHalt();
      const updated = {
        ...profile.mapping,
        enabled: !profile.mapping.enabled,
        verified: true
      };
      await api<Status>('/mappings', 'PUT', updated);
      await onRefresh();
      setNotice(`Gesture '${profile.label}' is now ${updated.enabled ? 'ACTIVE' : 'INACTIVE'}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to toggle gesture state.');
    }
  };

  // Management: Save edited profile
  const saveEditedProfile = async () => {
    if (!editingProfile) return;
    try {
      onHalt();
      await api<Status>(`/profiles/${encodeURIComponent(editingProfile.label)}`, 'PUT', {
        description: editDescription,
        accessibility_notes: editAccessibility,
        action: editAction,
        enabled: editingProfile.mapping.enabled
      });
      await onRefresh();
      setNotice(`Updated '${editingProfile.label}' successfully.`);
      setEditingProfile(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update profile.');
    }
  };

  // Management: Delete profile
  const deleteProfile = async (label: string) => {
    if (!window.confirm(`Permanently delete '${label}' and its stored training samples?`)) return;
    try {
      onHalt();
      await api<Status>(`/profiles/${encodeURIComponent(label)}`, 'DELETE');
      await onRefresh();
      setNotice(`Deleted gesture profile '${label}'.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete profile.');
    }
  };

  // Management: Record additional samples
  const startAddSamples = (label: string) => {
    onHalt();setAddingSamplesTo(label);const epoch=++captureEpoch.current;let left=3;
    const advance=()=>{
      if(!mounted.current||epoch!==captureEpoch.current)return;
      if(left===0){setAddSamplesCountdown(null);void executeAddSamples(label);return;}
      setAddSamplesCountdown(left--);countdownTimer.current=setTimeout(advance,700);
    };advance();
  };

  const executeAddSamples = async (label: string) => {
    setIsRecordingAdditional(true);const epoch=captureEpoch.current;
    try {
      const batch: {landmarks: number[][]; source: 'simulation' | 'camera'}[] = [];
      for (let i = 0; i < 8; i++) {
        const pts = await getPointsRef.current(true);
        if(!mounted.current||epoch!==captureEpoch.current)return;
        if (pts) batch.push({landmarks: pts, source: mode});
        await new Promise(r => setTimeout(r, 180));
      }
      if(!mounted.current||epoch!==captureEpoch.current)return;
      if (batch.length < 4) {
        throw new Error('Not enough frames detected. Please keep hand visible.');
      }
      await api<Status>(`/profiles/${encodeURIComponent(label)}/samples`, 'POST', {
        samples: batch,
        source: mode
      });
      await onRefresh();
      setNotice(`Added ${batch.length} samples to '${label}'. Model updated.`);
      setAddingSamplesTo(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add samples.');
    } finally {
      setIsRecordingAdditional(false);
      setAddSamplesCountdown(null);
    }
  };

  // AI Suggestions
  const suggestions: {id: string; title: string; explanation: string; actionText?: string; onAction?: () => void}[] = [];
  status.profiles.forEach(p => {
    if (p.training_count < 12) {
      suggestions.push({
        id: `samples-${p.label}`,
        title: `Add training samples: ${p.label}`,
        explanation: `'${p.label}' currently has ${p.training_count} training examples. Adding 4-8 natural variations enhances recognition stability.`,
        actionText: 'Add Samples',
        onAction: () => startAddSamples(p.label)
      });
    }
  });

  const visibleSuggestions = suggestions.filter(s => !dismissedSuggestions.includes(s.id));

  return (
    <div className="gesture-lab-container">
      {/* Top Navigation Tabs */}
      <div className="section-heading mb-4">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Hand className="text-teal-600" size={24} />
            Personalized Gesture Lab
          </h2>
          <p className="text-xs text-gray-500 mt-1">
            Capture, label, map an action, and train your gesture with immediate activation.
          </p>
        </div>
        <div className="tabs">
          <button
            className={activeTab === 'wizard' ? 'selected' : ''}
            onClick={() => setActiveTab('wizard')}
          >
            <PlusCircle size={14} className="inline mr-1" />
            Create & Train Gesture
          </button>
          <button
            className={activeTab === 'management' ? 'selected' : ''}
            onClick={() => setActiveTab('management')}
          >
            <Layers size={14} className="inline mr-1" />
            Gesture Management ({status.profiles.length})
          </button>
        </div>
      </div>

      {confirmationProfile ? (
        <div className="flex items-center justify-between p-3 bg-emerald-50 border border-emerald-200 rounded-lg mb-4 text-xs">
          <div className="flex items-center gap-2 text-emerald-800">
            <ShieldCheck size={16} className="text-emerald-600 flex-shrink-0" />
            <span>
              <strong>Two-Step Safety Active:</strong> Confirmation symbol for {mode} mode is <strong>"{confirmationProfile.label}"</strong> ({pretty(confirmationProfile.mapping.action)}).
            </span>
          </div>
          <span className="font-mono text-[10px] bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded font-bold">
            CONFIRMATION CONFIDENCE ≥ 10% · FAST VERIFICATION
          </span>
        </div>
      ) : (
        <div className="flex items-center justify-between p-3 bg-amber-50 border border-amber-200 rounded-lg mb-4 text-xs">
          <div className="flex items-center gap-2 text-amber-800">
            <ShieldAlert size={16} className="text-amber-600 flex-shrink-0" />
            <span>
              <strong>Two-Step Safety:</strong> No confirmation gesture enrolled for {mode} mode. In two-step verification, actions require a separate confirmation symbol (default: "Thumbs Up").
            </span>
          </div>
          <button
            className="px-2.5 py-1 bg-amber-700 hover:bg-amber-800 text-white rounded text-[11px] font-semibold cursor-pointer"
            onClick={quickEnrollThumbsUp}
          >
            + Pre-fill Thumbs Up Wizard
          </button>
        </div>
      )}

      {/* Optional AI Advisor Suggestions */}
      {visibleSuggestions.length > 0 && (
        <div className="ai-advisor-strip mb-4 p-3 bg-teal-50 border border-teal-200 rounded-lg">
          <div className="flex items-start gap-3">
            <Sparkles className="text-teal-700 mt-0.5 flex-shrink-0" size={18} />
            <div className="flex-1 text-xs">
              <strong>AI Lab Advisor:</strong>
              <div className="mt-1 space-y-1">
                {visibleSuggestions.slice(0, 2).map(s => (
                  <div key={s.id} className="flex items-center justify-between gap-2 py-0.5">
                    <span>
                      <strong>{s.title}:</strong> {s.explanation}
                    </span>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {s.onAction && (
                        <button
                          className="px-2 py-0.5 bg-teal-700 text-white rounded text-[10px] hover:bg-teal-800"
                          onClick={s.onAction}
                        >
                          {s.actionText}
                        </button>
                      )}
                      <button
                        className="text-gray-400 hover:text-gray-600 text-[10px]"
                        onClick={() => setDismissedSuggestions(prev => [...prev, s.id])}
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 1: CREATION WIZARD (STREAMLINED 4 STEPS) ── */}
      {activeTab === 'wizard' && (
        <div className="wizard-layout grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Main Wizard Card */}
          <div className="lg:col-span-8 card p-6">
            {/* Step Progress Tracker */}
            <div className="steps flex justify-between mb-6 pb-4 border-b border-gray-100 overflow-x-auto">
              {[
                {idx: 1, name: 'Capture'},
                {idx: 2, name: 'Label'},
                {idx: 3, name: 'Action'},
                {idx: 4, name: 'Train & Activate'}
              ].map(s => (
                <span
                  key={s.idx}
                  className={`flex items-center gap-2 text-xs cursor-pointer ${
                    step === s.idx ? 'current font-semibold text-teal-700' : step > s.idx ? 'done text-teal-600' : 'text-gray-400'
                  }`}
                  onClick={() => {
                    if (s.idx < step) setStep(s.idx as any);
                  }}
                >
                  <b className={`w-6 h-6 rounded-full grid place-items-center text-xs ${
                    step === s.idx ? 'bg-teal-700 text-white' : step > s.idx ? 'bg-teal-100 text-teal-800' : 'border border-gray-300'
                  }`}>
                    {step > s.idx ? <Check size={12} /> : s.idx}
                  </b>
                  <span className="hidden sm:inline">{s.name}</span>
                </span>
              ))}
            </div>

            {/* STEP 1: CAPTURE GESTURE */}
            {step === 1 && (
              <div className="step-content space-y-4">
                <div className="heading">
                  <h3 className="text-base font-semibold">Step 1 — Capture User-Defined Gesture</h3>
                  <p className="text-xs text-gray-500">
                    Perform your gesture using {mode === 'camera' ? 'your camera' : 'synthetic landmarks'}. Keep your hand centered and hold the pose steady.
                  </p>
                </div>

                {/* Tracking Quality Pill */}
                <div className={`p-2.5 rounded-md flex items-center justify-between text-xs border ${
                  trackingQuality.status === 'good'
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                    : trackingQuality.status === 'missing'
                    ? 'bg-rose-50 text-rose-800 border-rose-200'
                    : 'bg-amber-50 text-amber-800 border-amber-200'
                }`}>
                  <div className="flex items-center gap-2">
                    {trackingQuality.status === 'good' ? (
                      <CheckCircle2 size={16} className="text-emerald-600" />
                    ) : (
                      <AlertTriangle size={16} className="text-amber-600" />
                    )}
                    <span><strong>Tracking Status:</strong> {trackingQuality.message}</span>
                  </div>
                  <span className="text-[10px] font-mono uppercase bg-white/70 px-2 py-0.5 rounded">
                    {mode}
                  </span>
                </div>

                {/* Duration Selector */}
                <div className="flex items-center gap-4 py-2 border-y border-gray-100">
                  <label className="text-xs font-medium text-gray-700">Recording Duration:</label>
                  <div className="flex gap-2">
                    {[2, 3, 5].map(sec => (
                      <button
                        key={sec}
                        className={`px-3 py-1 text-xs rounded border ${
                          durationSec === sec
                            ? 'bg-teal-700 text-white border-teal-700'
                            : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                        }`}
                        onClick={() => setDurationSec(sec)}
                        disabled={isRecording}
                      >
                        {sec} seconds ({sec * 5} frames)
                      </button>
                    ))}
                  </div>
                </div>

                {/* Recording Status & Countdown Display */}
                {countdown !== null && (
                  <div className="p-6 bg-teal-50 border border-teal-200 rounded-lg text-center animate-pulse">
                    <span className="text-xs font-semibold text-teal-800 uppercase tracking-widest block mb-1">
                      Get Ready
                    </span>
                    <strong className="text-4xl font-bold text-teal-700">{countdown}</strong>
                    <p className="text-xs text-teal-600 mt-1">Position your hand and hold the pose...</p>
                  </div>
                )}

                {isRecording && (
                  <div className="p-4 bg-emerald-50 border border-emerald-300 rounded-lg text-center">
                    <span className="inline-block w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping mr-2" />
                    <strong className="text-sm font-semibold text-emerald-900">
                      RECORDING IN PROGRESS... HOLD STEADY
                    </strong>
                    <div className="meter mt-3">
                      <span className="animate-pulse bg-emerald-600" style={{width: '100%'}} />
                    </div>
                  </div>
                )}

                {/* Controls */}
                <div className="flex flex-wrap items-center gap-3 pt-2">
                  {!isRecording ? (
                    <button
                      className="button flex items-center gap-2"
                      onClick={startRecording}
                      disabled={countdown !== null || (mode === 'camera' && !cameraActive)}
                    >
                      <Play size={15} />
                      {capturedSamples.length === 0 ? 'Start Recording Gesture' : 'Record Another Take'}
                    </button>
                  ) : (
                    <button className="button secondary" onClick={stopRecording}>
                      <X size={15} /> Stop Recording
                    </button>
                  )}

                  {capturedSamples.length > 0 && (
                    <button
                      className="button secondary text-rose-600 border-rose-200 hover:bg-rose-50"
                      onClick={() => setCapturedSamples([])}
                      disabled={isRecording}
                    >
                      <RotateCcw size={15} /> Reset Samples
                    </button>
                  )}

                  {capturedSamples.length >= 8 && (
                    <button
                      className="button bg-emerald-700 hover:bg-emerald-800 text-white ml-auto"
                      onClick={() => setStep(2)}
                      disabled={isRecording}
                    >
                      Continue to Step 2: Name & Label ({capturedSamples.length} frames) →
                    </button>
                  )}
                </div>

                {/* Samples Collection Summary */}
                {capturedSamples.length > 0 && (
                  <div className="p-3 bg-gray-50 border border-gray-200 rounded-md text-xs flex justify-between items-center">
                    <span>
                      ✓ <strong>{capturedSamples.length} landmark frames captured</strong> ({Math.round(capturedSamples.length * 0.75)} train / {Math.round(capturedSamples.length * 0.25)} test reserved)
                    </span>
                    <span className="text-gray-500">
                      {capturedSamples.length >= 12 ? 'Excellent sample size' : 'Minimum 8 required'}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* STEP 2: NAME AND LABEL */}
            {step === 2 && (
              <div className="step-content space-y-4">
                <div className="heading">
                  <h3 className="text-base font-semibold">Step 2 — User-Defined Name and Label</h3>
                  <p className="text-xs text-gray-500">
                    Define what this gesture is called. You control the name and meaning completely.
                  </p>
                </div>

                <div>
                  <label className="field-label" htmlFor="gesture-name">
                    Gesture Name / Label <span className="text-rose-500">*</span>
                  </label>
                  <input
                    id="gesture-name"
                    type="text"
                    maxLength={40}
                    placeholder="e.g. My Zoom Gesture, Pinch Forward, Peace Sign"
                    value={gestureName}
                    onChange={e => setGestureName(e.target.value)}
                  />
                  {status.profiles.some(p => p.label.toLowerCase() === gestureName.trim().toLowerCase()) && (
                    <p className="text-amber-600 text-xs mt-1">
                      ⚠ A gesture with this name already exists. Saving will replace its existing profile.
                    </p>
                  )}
                </div>

                <div>
                  <label className="field-label" htmlFor="gesture-desc">
                    Gesture Description (Optional)
                  </label>
                  <input
                    id="gesture-desc"
                    type="text"
                    maxLength={200}
                    placeholder="e.g. Open hand flat toward camera with thumb relaxed"
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                  />
                </div>

                <div>
                  <label className="field-label">Gesture Type</label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-1">
                    <div
                      className={`p-3 rounded-lg border cursor-pointer text-xs ${
                        gestureType === 'static' ? 'border-teal-600 bg-teal-50' : 'border-gray-200 bg-white'
                      }`}
                      onClick={() => setGestureType('static')}
                    >
                      <strong className="block text-sm text-teal-900">Static Pose</strong>
                      <span className="text-gray-500 text-[11px]">
                        Multi-frame steady hand pose with temporal stability and dwell validation. (Recommended)
                      </span>
                    </div>

                    <div
                      className={`p-3 rounded-lg border cursor-pointer text-xs ${
                        gestureType === 'dynamic' ? 'border-teal-600 bg-teal-50' : 'border-gray-200 bg-white'
                      }`}
                      onClick={() => setGestureType('dynamic')}
                    >
                      <strong className="block text-sm text-teal-900">Dynamic Gesture</strong>
                      <span className="text-gray-500 text-[11px]">
                        Custom sequence learning is not implemented. Live left/right swipes use a separate built-in motion detector.
                      </span>
                    </div>
                  </div>
                </div>

                <div>
                  <label className="field-label" htmlFor="accessibility-notes">
                    Accessibility / Motor Preference Notes (Optional)
                  </label>
                  <input
                    id="accessibility-notes"
                    type="text"
                    maxLength={200}
                    placeholder="e.g. Accommodates limited index finger extension"
                    value={accessibilityNotes}
                    onChange={e => setAccessibilityNotes(e.target.value)}
                  />
                </div>

                <div className="flex justify-between items-center pt-4 border-t border-gray-100">
                  <button className="button secondary" onClick={() => setStep(1)}>
                    ← Back to Capture
                  </button>
                  <button
                    className="button"
                    disabled={!/^[A-Za-z0-9 _-]{1,40}$/.test(gestureName.trim())}
                    onClick={() => setStep(3)}
                  >
                    Continue to Step 3: Configure Action →
                  </button>
                </div>
              </div>
            )}

            {/* STEP 3: CONFIGURE ACTION */}
            {step === 3 && (
              <div className="step-content space-y-5">
                <div className="heading">
                  <h3 className="text-base font-semibold">Step 3 — Configure Associated Action</h3>
                  <p className="text-xs text-gray-700 font-medium mt-1">
                    "What should AirControl AI do when this gesture is recognized?"
                  </p>
                </div>

                {/* Option A: Direct Selection */}
                <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                  <label className="text-xs font-semibold uppercase tracking-wider text-gray-600 block mb-2">
                    Method A: Select from Supported Action Registry
                  </label>
                  <select
                    className="w-full"
                    value={selectedAction}
                    onChange={e => setSelectedAction(e.target.value as Command)}
                  >
                    {commands.map(cmd => (
                      <option key={cmd} value={cmd}>
                        {pretty(cmd)}
                      </option>
                    ))}
                  </select>
                  {selectedAction === 'confirm_pending' && (
                    <p className="text-xs text-amber-900 mt-2 bg-amber-100/70 p-2.5 rounded border border-amber-200">
                      <strong>Confirmation Symbol:</strong> When any other gesture requests an action, performing this gesture with ≥10% confidence immediately authorizes and executes the action.
                    </p>
                  )}
                </div>

                {/* Option B: Natural Language Assistant */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                  <div className="flex items-center gap-2">
                    <Sparkles size={16} className="text-purple-600" />
                    <label className="text-xs font-semibold uppercase tracking-wider text-purple-900">
                      Method B: Describe in Natural Language
                    </label>
                  </div>
                  <input
                    type="text"
                    value={naturalDesc}
                    onChange={e => setNaturalDesc(e.target.value)}
                    placeholder="e.g. When I hold this gesture, advance to the next image slice."
                  />
                  <div className="flex justify-end">
                    <button
                      className="button secondary text-xs py-1"
                      onClick={interpretWithAssistant}
                      disabled={isProposing || !naturalDesc.trim()}
                    >
                      <Sparkles size={13} /> {isProposing ? 'Analyzing…' : 'Interpret with AI Assistant'}
                    </button>
                  </div>

                  {assistantProposal && (
                    <div className="p-3 bg-purple-50 border border-purple-200 rounded-md text-xs mt-2">
                      <span className="badge amber mb-1">Proposal</span>
                      <strong className="block text-sm text-purple-900 mt-1">
                        Suggested Action: {pretty(assistantProposal.action)}
                      </strong>
                      <p className="text-purple-700 mt-1">{assistantProposal.explanation}</p>
                      <div className="flex gap-2 mt-2">
                        <button
                          className="button text-xs py-1 bg-purple-700 text-white"
                          onClick={() => {
                            setSelectedAction(assistantProposal.action);
                            setNotice(`Accepted assistant suggestion: ${pretty(assistantProposal.action)}`);
                          }}
                        >
                          Accept Proposal
                        </button>
                        <button
                          className="button secondary text-xs py-1"
                          onClick={() => setAssistantProposal(null)}
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Summary */}
                <div className="p-3 bg-teal-50 border border-teal-200 rounded-md text-xs flex justify-between items-center">
                  <span>Selected Mapping:</span>
                  <strong className="text-teal-900 text-sm">
                    {gestureName} → {pretty(selectedAction)}
                  </strong>
                </div>

                <div className="flex justify-between items-center pt-4 border-t border-gray-100">
                  <button className="button secondary" onClick={() => setStep(2)}>
                    ← Back to Label
                  </button>
                  <button className="button" onClick={() => setStep(4)}>
                    Continue to Step 4: Train & Activate →
                  </button>
                </div>
              </div>
            )}

            {/* STEP 4: TRAIN & DIRECT ACTIVATION (NO VERIFICATION BLOCKERS) */}
            {step === 4 && (
              <div className="step-content space-y-4">
                <div className="heading">
                  <h3 className="text-base font-semibold">Step 4 — Train & Activate</h3>
                  <p className="text-xs text-gray-500">
                    Review your configuration below. Training fits the classifier instantly and makes your gesture ready for live hands-free control.
                  </p>
                </div>

                <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg space-y-2 text-xs">
                  <div className="flex justify-between py-1 border-b border-gray-200">
                    <span className="text-gray-500">Gesture Name:</span>
                    <strong>{gestureName}</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-200">
                    <span className="text-gray-500">Mapped Command:</span>
                    <strong className="text-teal-800">{pretty(selectedAction)}</strong>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-200">
                    <span className="text-gray-500">Collected Samples:</span>
                    <strong>{capturedSamples.length} landmark frames</strong>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-gray-500">Gesture Type:</span>
                    <strong>{gestureType}</strong>
                  </div>
                </div>

                {!trainingDone ? (
                  <div className="flex flex-col sm:flex-row gap-3 pt-2">
                    <button
                      className="button bg-emerald-700 hover:bg-emerald-800 text-white flex-1 justify-center py-2.5"
                      onClick={() => trainAndSaveGesture(true)}
                      disabled={isTraining}
                    >
                      <CheckCircle2 size={16} />
                      {isTraining ? 'Training Classifier…' : 'Train & Activate Immediately'}
                    </button>
                    <button
                      className="button secondary flex-1 justify-center py-2.5"
                      onClick={() => trainAndSaveGesture(false)}
                      disabled={isTraining}
                    >
                      Train & Save as Inactive
                    </button>
                  </div>
                ) : (
                  <div className="p-4 bg-emerald-50 border border-emerald-300 rounded-lg text-emerald-900 text-xs text-center space-y-2">
                    <CheckCircle2 size={24} className="mx-auto text-emerald-600" />
                    <strong className="block text-sm">Gesture Trained and Ready! ({trainingDurationMs} ms)</strong>
                    <p>Your gesture mapping has been integrated into the live recognition pipeline.</p>
                  </div>
                )}

                <div className="flex justify-between items-center pt-4 border-t border-gray-100">
                  <button className="button secondary" onClick={() => setStep(3)} disabled={isTraining}>
                    ← Back to Action
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Visual Stage & Landmarks Feedback */}
          <div className="lg:col-span-4 space-y-4">
            <div className="card p-4">
              <div className="card-heading flex justify-between items-center mb-3">
                <span className="eyebrow">VISUAL FEEDBACK</span>
                <span className="badge gray">{mode}</span>
              </div>

              {/* Hand Stage */}
              <div className="hand-stage relative overflow-hidden bg-slate-900 rounded-lg h-56 flex items-center justify-center">
                {mode === 'camera' && cameraActive ? (
                  <>
                    <video
                      ref={cameraVideoRef}
                      autoPlay
                      playsInline
                      muted
                      className="absolute inset-0 w-full h-full object-cover transform scale-x-[-1]"
                    />
                    {currentLiveLandmarks && (
                      <svg viewBox="0 0 300 260" className="landmarks absolute inset-0 w-full h-full pointer-events-none transform scale-x-[-1]">
                        {[0,1,2,3,4].map(f => (
                          <polyline
                            key={f}
                            points={[0,...[1,2,3,4].map(j => f * 4 + j)]
                              .map(i => `${currentLiveLandmarks[i][0] * 300},${currentLiveLandmarks[i][1] * 260}`)
                              .join(' ')}
                            fill="none"
                            stroke="#5dc3a4"
                            strokeWidth="2.5"
                          />
                        ))}
                        {currentLiveLandmarks.map((p, i) => (
                          <circle
                            key={i}
                            cx={p[0] * 300}
                            cy={p[1] * 260}
                            r={i % 4 === 0 ? 5 : 3.5}
                            fill={i === 0 ? '#ff7b72' : '#bcf4da'}
                          />
                        ))}
                      </svg>
                    )}
                  </>
                ) : currentLiveLandmarks ? (
                  <svg viewBox="0 0 300 260" className="landmarks w-full h-full">
                    {[0,1,2,3,4].map(f => (
                      <polyline
                        key={f}
                        points={[0,...[1,2,3,4].map(j => f * 4 + j)]
                          .map(i => `${currentLiveLandmarks[i][0] * 300},${currentLiveLandmarks[i][1] * 260}`)
                          .join(' ')}
                        fill="none"
                        stroke="#5dc3a4"
                        strokeWidth="2.5"
                      />
                    ))}
                    {currentLiveLandmarks.map((p, i) => (
                      <circle
                        key={i}
                        cx={p[0] * 300}
                        cy={p[1] * 260}
                        r={i % 4 === 0 ? 5 : 3.5}
                        fill={i === 0 ? '#ff7b72' : '#bcf4da'}
                      />
                    ))}
                  </svg>
                ) : (
                  <div className="text-gray-500 text-xs text-center p-4">
                    <Hand size={42} className="mx-auto mb-2 opacity-40" />
                    <span>No landmarks stream</span>
                  </div>
                )}
                <span className="stage-label absolute bottom-2 left-2 text-[10px] font-mono text-teal-400 bg-black/50 px-1.5 py-0.5 rounded">
                  {mode === 'camera' ? 'CAMERA STREAM' : `SYNTHETIC POSE: ${poseNames[pose]}`}
                </span>
              </div>

              {/* Camera Enable Button */}
              {mode === 'camera' && !cameraActive && (
                <button
                  className="button secondary w-full mt-3 text-xs"
                  onClick={onEnableCamera}
                >
                  <Video size={14} /> Start Camera Feed
                </button>
              )}

              <div className="mt-3 text-[11px] text-gray-500 space-y-1">
                <p>• Features use palm-normalized hand distances and finger proportions.</p>
                <p>• Newly trained gestures can be activated immediately or kept on standby.</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 2: GESTURE MANAGEMENT (DIRECT ACTIVE/INACTIVE CONTROLS) ── */}
      {activeTab === 'management' && (
        <div className="management-layout space-y-6">
          <div className="card p-6">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="text-base font-semibold">User Gesture Library</h3>
                <p className="text-xs text-gray-500">
                  Manage your enrolled gestures, edit actions, add natural samples, and toggle them active or inactive anytime.
                </p>
              </div>
              <button
                className="button text-xs"
                onClick={() => {
                  resetWizard();
                  setActiveTab('wizard');
                }}
              >
                <Plus size={14} /> Create New Gesture
              </button>
            </div>

            {status.profiles.length === 0 ? (
              <div className="empty p-12 text-center text-gray-500">
                <Hand size={48} className="mx-auto mb-3 opacity-30" />
                <strong>No gestures enrolled yet.</strong>
                <p className="text-xs mt-1">Create your first gesture using the interactive wizard.</p>
                <button
                  className="button mt-4 mx-auto text-xs"
                  onClick={() => setActiveTab('wizard')}
                >
                  Start Creation Wizard
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-gray-50 text-gray-500 uppercase text-[10px]">
                    <tr>
                      <th className="p-3">Gesture Name</th>
                      <th className="p-3">Type</th>
                      <th className="p-3">Mapped Action</th>
                      <th className="p-3">Samples</th>
                      <th className="p-3">Status</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {status.profiles.map(p => (
                      <tr key={p.label} className="hover:bg-gray-50/50">
                        <td className="p-3 font-semibold text-gray-800">
                          {p.label}
                          {p.description && (
                            <span className="block text-[10px] font-normal text-gray-500">
                              {p.description}
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-gray-600">
                          {p.gesture_type || 'static'}
                        </td>
                        <td className="p-3 font-mono text-teal-800">
                          {pretty(p.mapping.action)}
                          {p.mapping.action === 'confirm_pending' && (
                            <span className="inline-block mt-0.5 px-1.5 py-0.2 bg-amber-100 text-amber-800 rounded text-[9px] font-bold">
                              CONFIRMATION SYMBOL
                            </span>
                          )}
                          <small className="block">Requires {Math.round(p.effective_threshold*100)}% confidence</small>
                        </td>
                        <td className="p-3 text-gray-600">
                          {p.training_count} train / {p.test_count} test
                        </td>
                        <td className="p-3">
                          <button
                            className={`px-3 py-1 rounded text-[11px] font-semibold cursor-pointer transition ${
                              p.mapping.enabled
                                ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm'
                                : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
                            }`}
                            onClick={() => toggleProfileActive(p)}
                            title="Click to toggle Active / Inactive"
                          >
                            {p.mapping.enabled ? 'ACTIVE' : 'INACTIVE'}
                          </button>
                        </td>
                        <td className="p-3 text-right space-x-2">
                          <button
                            className="p-1 hover:text-teal-700"
                            title="Edit Gesture"
                            onClick={() => {
                              setEditingProfile(p);
                              setEditAction(p.mapping.action);
                              setEditDescription(p.description || '');
                              setEditAccessibility(p.accessibility_notes || '');
                            }}
                          >
                            <Edit3 size={15} />
                          </button>
                          <button
                            className="p-1 hover:text-teal-700"
                            title="Add Training Samples"
                            onClick={() => startAddSamples(p.label)}
                          >
                            <PlusCircle size={15} />
                          </button>
                          <button
                            className="p-1 text-rose-600 hover:text-rose-800"
                            title="Delete Gesture"
                            onClick={() => deleteProfile(p.label)}
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Edit Profile Modal */}
          {editingProfile && (
            <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
              <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
                <div className="flex justify-between items-center pb-2 border-b">
                  <h3 className="font-semibold text-base">Edit Gesture: {editingProfile.label}</h3>
                  <button onClick={() => setEditingProfile(null)}><X size={18} /></button>
                </div>

                <div>
                  <label className="field-label">Mapped Action</label>
                  <select
                    value={editAction}
                    onChange={e => setEditAction(e.target.value as Command)}
                  >
                    {commands.map(cmd => (
                      <option key={cmd} value={cmd}>{pretty(cmd)}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="field-label">Description</label>
                  <input
                    type="text"
                    value={editDescription}
                    onChange={e => setEditDescription(e.target.value)}
                  />
                </div>

                <div>
                  <label className="field-label">Accessibility Notes</label>
                  <input
                    type="text"
                    value={editAccessibility}
                    onChange={e => setEditAccessibility(e.target.value)}
                  />
                </div>

                <div className="flex justify-end gap-2 pt-3 border-t">
                  <button className="button secondary" onClick={() => setEditingProfile(null)}>
                    Cancel
                  </button>
                  <button className="button" onClick={saveEditedProfile}>
                    Save Changes
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Adding Samples In-Progress Notification */}
          {addingSamplesTo && (
            <div className="fixed bottom-6 right-6 bg-slate-900 text-white p-4 rounded-xl shadow-2xl z-50 max-w-sm text-xs space-y-2 border border-slate-700">
              <strong>Adding Samples to '{addingSamplesTo}'</strong>
              {addSamplesCountdown !== null ? (
                <p className="text-teal-400">Position hand... Recording in {addSamplesCountdown}...</p>
              ) : isRecordingAdditional ? (
                <p className="text-emerald-400 animate-pulse">Capturing frames... hold pose...</p>
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
