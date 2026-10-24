import {CaptureCoordinator} from './capture';
import {SwipeDetector} from './motion';
import {useState,useEffect,useRef,useCallback,type ReactNode} from 'react';
import {Activity,ArrowDown,ArrowLeft,ArrowRight,ArrowUp,ArrowUpRight,Check,CheckCircle2,ChevronRight,ChevronLeft,CircleHelp,Command as CommandIcon,Download,Hand,Layers,LayoutDashboard,LockKeyhole,Maximize2,Move,Pause,Play,Plus,Radio,RotateCcw,ScanLine,Settings2,ShieldCheck,ShieldAlert,Sparkles,Trash2,Undo2,Video,X,ZoomIn,ZoomOut,FlaskConical} from 'lucide-react';
import {api,cameraError} from './api';
import {Phantom} from './Phantom';
import {GestureLab} from './GestureLab';
import {commands,pretty,type Status,type Command,type Mapping,type Settings,type Recognition,type Event} from './types';

const pages=[['Overview',LayoutDashboard],['Gesture Lab',FlaskConical],['Live gesture control',Radio],['SafeIntent event log',ShieldCheck],['AI setup assistant',Sparkles],['Settings & privacy',Settings2]] as const;
const poseNames=['Open palm','Closed fist','Index finger','Two fingers','Thumb & pinky','Thumbs up'];
const initialSettings:Settings={threshold:.10,smoothing:.20,dwell_ms:300,cooldown_ms:650,sensitivity:1.35};
const empty:Status={control_revision:0,boot_id:'',zoom_minimum:.10,profiles:[],settings:initialSettings,state:'IDLE',viewer:{slice:47,zoom:1,x:0,y:0},events:[],benchmarks:[],model_ready:false,camera_model_available:false};
const pause=(ms:number)=>new Promise(r=>setTimeout(r,ms));
function Button({children,onClick,secondary=false,disabled=false,className=''}:{children:ReactNode;onClick:()=>void;secondary?:boolean;disabled?:boolean;className?:string}){return <button disabled={disabled} className={`${secondary?'button secondary':'button'} ${className}`} onClick={onClick}>{children}</button>}
function IconButton({label,onClick,children}:{label:string;onClick:()=>void;children:ReactNode}){return <button className="icon-button" title={label} aria-label={label} onClick={onClick}>{children}</button>}
function Badge({children,tone='green'}:{children:ReactNode;tone?:string}){return <span className={'badge '+tone}><span/>{children}</span>}

export default function App(){
 const [cameraActive,setCameraActive]=useState(false);
 const [page,setPage]=useState(0),[data,setData]=useState<Status>(empty),[connected,setConnected]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[mode,setMode]=useState<'simulation'|'camera'>('camera'),[pose,setPose]=useState(0),[uncertain,setUncertain]=useState(false),[holding,setHolding]=useState(false),[running,setRunning]=useState(false),[recognition,setRecognition]=useState<Recognition|null>(null),[points,setPoints]=useState<number[][]|null>(null),[busy,setBusy]=useState(false);
 const [label,setLabel]=useState('Open palm'),[action,setAction]=useState<Command>('zoom_in'),[samples,setSamples]=useState<{landmarks:number[][];source:'simulation'|'camera'}[]>([]),[step,setStep]=useState(0),[capturing,setCapturing]=useState(false),[proposal,setProposal]=useState<Mapping|null>(null),[assistantText,setAssistantText]=useState('When I make this gesture, move to the next image slice.'),[selected,setSelected]=useState(''),[settings,setSettings]=useState<Settings>(initialSettings),[filter,setFilter]=useState('all');
 const captureCoordinator=useRef(new CaptureCoordinator<number[][]|null>()), revision=useRef(0), boot=useRef(''), healthy=useRef(false), inputRequest=useRef<AbortController|null>(null);
 const swipeDetector=useRef(new SwipeDetector());
 const video=useRef<HTMLVideoElement>(null),previewVideo=useRef<HTMLVideoElement>(null),stream=useRef<MediaStream|null>(null),serial=useRef(0),started=useRef(0),stop=useRef(true),frameIndex=useRef(0),captureStop=useRef(false);
 const acceptStatus=useCallback((value:Status)=>{revision.current=value.control_revision;boot.current=value.boot_id;healthy.current=true;setData(value);setConnected(true);},[]);
 const stopLocally=useCallback(()=>{stop.current=true;serial.current++;captureStop.current=true;inputRequest.current?.abort();captureCoordinator.current.cancel();swipeDetector.current.reset();setRunning(false);setHolding(false);setRecognition(null);},[]);
 const refresh=useCallback(async()=>{const value=await api<Status>('/status');acceptStatus(value);setSettings(value.settings);return value;},[acceptStatus]);
 useEffect(()=>{revision.current=data.control_revision;},[data.control_revision]);
 const attempt=useCallback(async(fn:()=>Promise<unknown>)=>{setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'Something went wrong.');}},[]);
 useEffect(()=>{refresh().catch(()=>{setError('Backend is unavailable. Start FastAPI on port 8000, then reconnect.');setConnected(false);});return()=>{stop.current=true;captureStop.current=true;captureCoordinator.current.cancel();inputRequest.current?.abort();stream.current?.getTracks().forEach(t=>t.stop());};},[refresh]);
 useEffect(()=>{window.scrollTo(0,0);if(!stop.current)halt();else captureCoordinator.current.cancel();},[page]);
 useEffect(()=>{if(notice){const id=setTimeout(()=>setNotice(''),6000);return()=>clearTimeout(id);}},[notice]);
 useEffect(()=>{const activeStream=stream.current;if(!activeStream)return;for(const element of [video.current,previewVideo.current]){if(!element)continue;if(element.srcObject!==activeStream)element.srcObject=activeStream;void element.play().catch(()=>{});}},[page,mode,cameraActive]);
 const changeState=async(state:'ARMED'|'PAUSED'|'IDLE')=>{
  swipeDetector.current.reset();if(state!=='ARMED')stopLocally();
  const generation=++serial.current;
  const value=await api<Status>('/state','POST',{state});
  if(generation!==serial.current){if(state==='ARMED')await api('/state','POST',{state:'PAUSED'});return;}
  acceptStatus(value);if(state==='ARMED'){stop.current=false;setRunning(true);}setNotice(`System ${state.toLowerCase()}.`);
 };
 const manual=useCallback(async(command:Command)=>{setData(await api<Status>('/viewer/action','POST',{action:command}));},[]);
 const halt=useCallback(()=>{stopLocally();attempt(async()=>{acceptStatus(await api<Status>('/state','POST',{state:'PAUSED'}));});},[attempt,stopLocally,acceptStatus]);
 useEffect(()=>{
  let cancelled=false;let timer:ReturnType<typeof setTimeout>;
  async function check(){
   try{
    const h=await api<{boot_id:string;control_revision:number;state:string}>('/health','GET',undefined,AbortSignal.timeout(2000));
    if(cancelled)return;
    const restarted=!!boot.current&&boot.current!==h.boot_id;
    if(restarted||!healthy.current){
     stopLocally();
     const value=await api<Status>('/state','POST',{state:'PAUSED'});
     if(cancelled)return;
     acceptStatus(value);setSettings(value.settings);setError('');
     setNotice('Backend connected. Activate control explicitly when ready.');
    }else if(!stop.current&&(h.state==='PAUSED'||h.state==='IDLE')){
     stopLocally();await refresh();
    }
    setConnected(true);
   }catch{
    if(!cancelled){healthy.current=false;setConnected(false);stopLocally();setData(d=>({...d,state:'DISCONNECTED'}));setError('Backend disconnected. Recognition stopped. Waiting for reconnection; activation will remain manual.');}
   }finally{if(!cancelled)timer=setTimeout(check,2000);}
  }
  timer=setTimeout(check,1000);
  return()=>{cancelled=true;clearTimeout(timer);};
 },[acceptStatus,refresh,stopLocally]);
 useEffect(()=>{const handler=(e:KeyboardEvent)=>{if(e.key==='Escape'){halt();return;}if(['INPUT','TEXTAREA','SELECT','BUTTON'].includes((e.target as HTMLElement).tagName))return;const map:Record<string,Command>={ArrowRight:'next_slice',ArrowLeft:'previous_slice','+':'zoom_in','=':'zoom_in','-':'zoom_out',r:'reset_view',w:'pan_up',a:'pan_left',s:'pan_down',d:'pan_right'};if(map[e.key]&&(page===0||page===2)){e.preventDefault();attempt(()=>manual(map[e.key]));}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[page,manual,halt,attempt]);
 async function enableCamera(){
  if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera capture requires localhost or HTTPS. Simulation is available.');
  if(!data.camera_model_available)throw new Error('Hand Landmarker model is missing. Run scripts/download-model.ps1 and reconnect.');
  try{
   stream.current?.getTracks().forEach(t=>t.stop());
   const activeStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:640},height:{ideal:480}},audio:false});
   stream.current=activeStream;
   setCameraActive(true);
   for(const element of [video.current,previewVideo.current]){if(!element)continue;element.srcObject=activeStream;await element.play();}
   setNotice('Camera is active. Frames stay on this computer.');
  }catch(e){stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;setCameraActive(false);throw new Error(cameraError(e));}
 }
 async function switchMode(value:'simulation'|'camera'){swipeDetector.current.reset();
  await changeState('IDLE');captureStop.current=true;setSamples([]);setStep(0);setMode(value);if(value==='camera'&&![1,2].includes(page))setPage(2);setPoints(null);setRecognition(null);stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;setCameraActive(false);
 }
 async function getPoints(forEnrollment=false){return captureCoordinator.current.read(signal=>capturePoints(forEnrollment,signal));}
 async function capturePoints(forEnrollment=false,signal?:AbortSignal){
  if(mode==='simulation'){
   if(!holding&&!forEnrollment)return null;
   const r=await api<{landmarks:number[][]}>(`/simulation/${pose}?seed=${++frameIndex.current}`,'GET',undefined,signal);
   if(uncertain&&!forEnrollment)r.landmarks=r.landmarks.map((p,i)=>[p[0]+Math.sin(i*7)*.16,p[1]+Math.cos(i*3)*.14,p[2]+.08*Math.sin(i)]);
   return r.landmarks;
  }
  if(!stream.current||!video.current)throw new Error('Start the camera before capturing or recognizing a gesture.');
  if(stream.current.getVideoTracks().every(track=>track.readyState!=='live'))throw new Error('The camera stream has stopped. Start the camera again.');
  if(video.current.readyState<HTMLMediaElement.HAVE_CURRENT_DATA){
   await new Promise<void>((resolve,reject)=>{
    const element=video.current;
    if(!element){reject(new Error('Camera video element is unavailable.'));return;}
    let settled=false;
    const cleanup=()=>{window.clearTimeout(timeout);element.removeEventListener('loadeddata',onLoaded);element.removeEventListener('error',onError);};
    const finish=(error?:Error)=>{if(settled)return;settled=true;cleanup();error?reject(error):resolve();};
    const onLoaded=()=>finish();
    const onError=()=>finish(new Error('Could not read the camera video stream.'));
    const timeout=window.setTimeout(()=>finish(new Error('No camera frame received. Check camera permission and try again.')),5000);
    element.addEventListener('loadeddata',onLoaded,{once:true});element.addEventListener('error',onError,{once:true});
   });
  }
  const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
  const context=canvas.getContext('2d');
  if(!context||!video.current.videoWidth)throw new Error('Camera is not ready yet. Wait for the preview and retry.');
  context.drawImage(video.current,0,0,640,480);
  return (await api<{landmarks:number[][]|null}>('/camera/landmarks','POST',{image:canvas.toDataURL('image/jpeg',.65)},signal)).landmarks;
 }
 useEffect(()=>{
  if(!running)return;
  let cancelled=false;let timer:ReturnType<typeof setTimeout>;
  const generation=++serial.current, controller=new AbortController();inputRequest.current=controller;
  const valid=()=>!cancelled&&!stop.current&&generation===serial.current;
  async function tick(){
   try{
    const landmarks=await getPoints();if(!valid())return;setPoints(landmarks);
    const control_revision=revision.current;
    if(mode==='camera'){
     const swipe=swipeDetector.current.feed(landmarks,performance.now());
     if(swipe){
      await api('/recognize','POST',{landmarks:null,source:mode,control_revision},controller.signal);
      if(!valid())return;
      const value=await api<Status>('/motion','POST',{action:swipe,source:mode,control_revision},controller.signal).catch((e:unknown)=>{
       if(e instanceof Error&&e.message.includes('cooldown'))return null;throw e;
      });
      if(valid()&&value){acceptStatus(value);setNotice(swipe==='next_slice'?'Swipe right: next image':'Swipe left: previous image');}
      return;
     }
    }
    const r=await api<Recognition>('/recognize','POST',{landmarks,source:mode,control_revision},controller.signal);
    if(!valid())return;
    revision.current=r.control_revision??revision.current;
    setRecognition(r);setData(d=>({...d,state:r.state,viewer:r.viewer,control_revision:revision.current}));
    if(r.state==='PAUSED'||r.state==='IDLE'){stopLocally();return;}
    if(r.action){const value=await api<Status>('/status','GET',undefined,controller.signal);if(valid())acceptStatus(value);}
   }catch(e){
    if(valid()){stopLocally();setError(e instanceof Error?e.message:'Recognition failed.');try{acceptStatus(await api<Status>('/state','POST',{state:'PAUSED'}));}catch{healthy.current=false;setConnected(false);}}
   }finally{if(valid())timer=setTimeout(tick,120);}
  }
  tick();return()=>{cancelled=true;controller.abort();captureCoordinator.current.cancel();clearTimeout(timer);};
 },[running,mode,pose,holding,uncertain]);
 async function capture(){
  setCapturing(true);captureStop.current=false;started.current=performance.now();setSamples([]);
  try{await changeState('IDLE');const collected:typeof samples=[];for(let i=0;i<12;i++){if(captureStop.current)break;const p=await getPoints(true);if(!p)throw new Error('No hand detected. Keep a hand visible and retry capture.');collected.push({landmarks:p,source:mode});setPoints(p);setSamples([...collected]);await pause(220);}if(collected.length===12)setStep(2);}finally{setCapturing(false);}
 }
 async function enroll(){setBusy(true);try{const value=await api<Status>('/enroll','POST',{mapping:{gesture_label:label,action,enabled:true,requires_confirmation:true,threshold:null},samples,elapsed_seconds:(performance.now()-started.current)/1000});setData(value);setSamples([]);setStep(0);setNotice('Gesture trained and mapping confirmed. Ready to activate.');setPage(2);}finally{setBusy(false);}}
 async function benchmark(){setBusy(true);try{await api('/benchmark','POST');await refresh();setNotice('Held-out evaluation complete. Results are calculated from test predictions.');}finally{setBusy(false);}}
 const latest=data.benchmarks.at(-1),activeCount=data.profiles.filter(p=>p.mapping.enabled).length;
 const navigate=(n:number)=>{setPage(n);if(n===3)attempt(refresh);};

 const inputPanel=<div className="card input-panel"><div className="card-heading"><div><span className="eyebrow">INPUT SOURCE</span><h3>Local camera</h3></div><Badge tone="green">Local only</Badge></div><div className="hand-stage relative overflow-hidden"><video ref={previewVideo} autoPlay playsInline muted aria-label="Live camera preview" style={{transform:'scaleX(-1)'}}/>{points&&<svg viewBox="0 0 300 260" className="landmarks absolute inset-0 w-full h-full pointer-events-none" style={{transform:'scaleX(-1)',position:'absolute',inset:0}}>{[0,1,2,3,4].map(f=><polyline key={f} points={[0,...[1,2,3,4].map(j=>f*4+j)].map(i=>`${points[i][0]*300},${points[i][1]*260}`).join(' ')} fill="none" stroke="#5dc3a4" strokeWidth="2.5"/>)}{points.map((p,i)=><circle key={i} cx={p[0]*300} cy={p[1]*260} r={i%4===0?5:3.5} fill={i===0?'#ff7b72':'#bcf4da'}/>)}</svg>}<span className="stage-label">LOCAL PROCESSING · NO RECORDING</span></div><Button secondary onClick={()=>cameraActive?(halt(),stream.current?.getTracks().forEach(t=>t.stop()),stream.current=null,setCameraActive(false)):attempt(enableCamera)}><Video size={16}/> {cameraActive?'Stop camera':'Start camera'}</Button><p className="muted small">Camera images are sent only to the local FastAPI server, processed in memory, and discarded.</p></div>;

 const viewerPanel=<div className="card viewer-card"><div className="card-heading"><div className="flex items-center gap-2"><Layers size={18}/><h3>Virtual imaging lab</h3></div><button className="text-button" onClick={()=>navigate(page===2?0:2)}>{page===2?'Overview':'Live control'} <ArrowUpRight size={15}/></button></div><div className="scan-stage"><div className="scan-meta"><span>AC-001 / SYNTHETIC PHANTOM</span><span>AXIAL · SERIES {Math.floor(data.viewer.slice/32)+1} / 4</span></div><Badge tone="dark">SIMULATED IMAGE</Badge><span className="orientation top">A</span><span className="orientation left">R</span><span className="orientation right">L</span><span className="orientation bottom">P</span><Phantom view={data.viewer}/><div className="scan-bottom"><span>SLICE {String(data.viewer.slice+1).padStart(2,'0')} / 128</span><span>{Math.round(data.viewer.zoom*100)}% ZOOM</span></div><div className="scan-scale">┬<br/>┤<br/>┤<br/>┤<br/>┴</div></div><div className="viewer-tools"><div><IconButton label="Previous slice" onClick={()=>attempt(()=>manual('previous_slice'))}><ChevronLeft size={18}/></IconButton><span>{data.viewer.slice+1} <em>/ 128</em></span><IconButton label="Next slice" onClick={()=>attempt(()=>manual('next_slice'))}><ChevronRight size={18}/></IconButton></div><div><IconButton label="Zoom out" onClick={()=>attempt(()=>manual('zoom_out'))}><ZoomOut size={18}/></IconButton><IconButton label="Zoom in" onClick={()=>attempt(()=>manual('zoom_in'))}><ZoomIn size={18}/></IconButton><i/><IconButton label="Pan left" onClick={()=>attempt(()=>manual('pan_left'))}><ArrowLeft size={16}/></IconButton><IconButton label="Pan up" onClick={()=>attempt(()=>manual('pan_up'))}><ArrowUp size={16}/></IconButton><IconButton label="Pan down" onClick={()=>attempt(()=>manual('pan_down'))}><ArrowDown size={16}/></IconButton><IconButton label="Pan right" onClick={()=>attempt(()=>manual('pan_right'))}><ArrowRight size={16}/></IconButton><i/><IconButton label="Reset view" onClick={()=>attempt(()=>manual('reset_view'))}><RotateCcw size={17}/></IconButton><IconButton label="Undo last action" onClick={()=>attempt(async()=>setData(await api<Status>('/viewer/undo','POST')))}><Undo2 size={17}/></IconButton></div></div><div className="series-chooser" aria-label="Synthetic image series">
 {['Series A · anatomy','Series B · ventricles','Series C · lobes','Series D · contrast'].map((name,i)=><button type="button" key={name} className={Math.floor(data.viewer.slice/32)===i?'selected':''} onClick={()=>attempt(async()=>setData(await api<Status>(`/viewer/series/${i}`,'POST')))}>{name}</button>)}
 <small>Camera: swipe right/left to browse all 128 slices while control is active</small>
</div></div>;
 const currentPending=recognition?.pending_verification||data.pending_verification;
 const currentContinuous=recognition?.continuous_zoom||data.continuous_zoom;

 const recognitionPanel=<div className="card recognition-panel">
  {currentPending&&<div className="pending-verification-box mb-3 p-3 bg-amber-50 border border-amber-300 rounded-lg" role="region" aria-label="Two-step gesture verification">
    <div className="flex items-start justify-between gap-2">
      <div className="flex items-start gap-2">
        <ShieldAlert className="text-amber-600 flex-shrink-0 mt-0.5" size={20}/>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-amber-800 bg-amber-200/70 px-1.5 py-0.5 rounded">
              TWO-STEP VERIFICATION REQUIRED
            </span>
            <span className="font-mono text-xs font-bold text-amber-900 bg-amber-200 px-2 py-0.5 rounded-full">
              {currentPending.timeout_remaining_seconds.toFixed(1)}s
            </span>
          </div>
          <h3 className="text-sm font-bold text-gray-900 mt-1">{currentPending.prompt}</h3>
        </div>
      </div>
      <button className="px-2 py-1 bg-amber-200 hover:bg-amber-300 text-amber-900 text-xs font-semibold rounded transition flex items-center gap-1 cursor-pointer" onClick={()=>attempt(async()=>setData(await api<Status>('/verification/cancel','POST')))} title="Cancel pending verification">
        <X size={13}/> Cancel
      </button>
    </div>
    <div className="mt-2.5">
      <div className="flex justify-between text-[11px] text-gray-600 mb-1">
        <span>Confirmation: <strong>Fast verification</strong> (instant on ≥ 10% conf)</span>
        <span>Symbol: <strong>{currentPending.verification_symbol}</strong></span>
      </div>
      <div className="meter bg-amber-200">
        <span style={{width:`${currentPending.dwell_progress*100}%`}} className="bg-amber-600"/>
      </div>
    </div>
    <p className="text-[10px] text-amber-800 mt-2">
      Safety lock: image action blocked until verified. Original gesture cannot self-confirm.
    </p>
  </div>}

  {currentContinuous&&<div className="continuous-zoom-box mb-3 p-3 bg-teal-50 border border-teal-300 rounded-lg" role="region" aria-label="Continuous zoom active">
    <div className="flex items-start justify-between gap-2">
      <div className="flex items-start gap-2">
        <ZoomIn className="text-teal-700 flex-shrink-0 mt-0.5" size={20}/>
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-teal-800 bg-teal-200/70 px-1.5 py-0.5 rounded">
            ACTIVE CONTINUOUS ZOOM
          </span>
          <h3 className="text-sm font-bold text-teal-950 mt-1">{currentContinuous.message}</h3>
        </div>
      </div>
      <button className="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold rounded transition flex items-center gap-1 cursor-pointer shadow-sm" onClick={()=>attempt(async()=>setData(await api<Status>('/viewer/action','POST',{action:'stop_zoom'})))}>
        <Pause size={13}/> Stop Zoom
      </button>
    </div>
    <p className="text-[10px] text-teal-800 mt-2">
      Hold <strong>{currentContinuous.initiating_gesture}</strong> steady. Stepping max 1/500ms (up to 20 steps, 10s max). Release hand or present Stop Zoom to cease.
    </p>
  </div>}

  <div className="card-heading"><h3>Recognition status</h3><Activity size={18}/></div>
  <div className="recognition-name">{recognition?.label||'Waiting for a gesture'}<span>{recognition?`${Math.round(recognition.confidence*100)}%`:'—'}</span></div>
  <div className="meter"><span style={{width:`${(recognition?.confidence||0)*100}%`}}/></div>
  <div className="flex justify-between small muted"><span>Model confidence</span><span>{recognition?.label?`${Math.round(recognition.effective_threshold*100)}% required`:`Zoom requires at least ${Math.round(data.zoom_minimum*100)}%`}</span></div>
  <div className="intent-state"><ShieldCheck size={20}/><div><strong>SafeIntent · {data.state}</strong><p>{recognition?.reason||(data.state==='DISCONNECTED'?'Backend disconnected. Execution is disabled until reconnection and explicit activation.':data.state==='PAUSED'?'Recognition is paused. Manual controls remain available.':data.state==='AWAITING_VERIFICATION'?'Action requested. Show confirmation symbol (Thumbs Up) to confirm.':data.state==='VERIFIED'?'Confirmed! Show original gesture again to begin.':'Arm the system, then present a trained gesture.')}</p></div></div>
  <dl className="execution-status" aria-live="polite">
    <div><dt>Safety state</dt><dd>{currentPending?'Awaiting Verification':currentContinuous?'Active Zoom':pretty(data.state)}</dd></div>
    <div><dt>Mapped action</dt><dd>{recognition?.mapped_action?pretty(recognition.mapped_action):'No prediction'}</dd></div>
    <div><dt>Confidence gate</dt><dd>{recognition?.label?(recognition.confidence_passed?'Passed':'Below required threshold'):'Waiting'}</dd></div>
    <div><dt>Stable dwell</dt><dd>{Math.round((recognition?.dwell_progress||0)*100)}% · {recognition?.stable_frames||0} frames</dd></div>
    <div><dt>Mapping / cooldown</dt><dd>{recognition?.mapping_status||'Waiting'} · {Math.ceil(recognition?.cooldown_remaining_ms||0)} ms</dd></div>
  </dl>
  <div className="mini-facts"><span>Dwell <strong>{data.settings.dwell_ms} ms</strong></span><span>Cooldown <strong>{data.settings.cooldown_ms} ms</strong></span></div>
 </div>;

 return <div className="app-shell"><video ref={video} autoPlay playsInline muted aria-hidden="true" style={{position:"fixed",width:1,height:1,opacity:0,pointerEvents:"none"}}/><aside className="sidebar"><a className="brand" href="#" onClick={e=>{e.preventDefault();navigate(0);}}><div className="brand-symbol"><Activity size={25}/></div><div>AirControl<span>AI</span><small>TOUCHLESS BY DESIGN</small></div></a><div className="workspace-label">RESEARCH WORKSPACE</div><nav>{pages.map(([name,Icon],i)=><button key={name} aria-label={name} title={name} className={page===i?'nav-item active':'nav-item'} onClick={()=>navigate(i)}><Icon size={18}/><span>{name}</span>{i===4&&<span className="local-tag">LOCAL</span>}{page===i&&<span className="nav-dot"/>}</button>)}</nav><div className="sidebar-bottom"><div className="privacy-box"><ShieldCheck size={22}/><strong>Private by default</strong><p>Your gestures stay on your device. Your focus stays where it matters.</p><button onClick={()=>navigate(5)}>Privacy & controls <ArrowUpRight size={14}/></button></div><div className="profile"><div className="avatar">AC</div><div>Demo workspace<small>Vibethon · ENCIDE</small></div><span className="status-dot"/></div></div></aside><div className="main-shell"><header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={14}/> <strong>{pages[page][0]}</strong></div><div className="topbar-right"><span className="connection"><span className={'status-dot '+(!connected?'offline':'')}/>{connected?'Backend connected':'Backend offline'}</span><span className="separator"/><span className="prototype-pill">RESEARCH PROTOTYPE</span><IconButton label="Open demonstration guide" onClick={()=>{setNotice('Demo: enroll a pose → activate → present gesture → release → test noisy input → Esc always pauses.');}}><CircleHelp size={19}/></IconButton></div></header><main><div className="page-heading"><div><div className="eyebrow">AIRCONTROL AI / {page===0?'MISSION CONTROL':pages[page][0].toUpperCase()}</div><h1>{page===0?'Precision, without the touch.':pages[page][0]}</h1><p>{['Your workspace for adaptive, touchless image interaction.','Teach the interface a static pose that works for you.','Follow every prediction from landmarks to a validated action.','A transparent record of predictions, decisions, and viewer actions.','Describe an interaction. Review the mapping. Stay in control.','Tune recognition to your preferences and manage local data.'][page]}</p></div><div className="heading-actions"><Button onClick={()=>attempt(()=>changeState(running?'PAUSED':'ARMED'))} disabled={!connected||capturing}>{running?<Pause size={16}/>:<Play size={16}/>} {running?'Pause control':'Activate control'}</Button></div></div>
 {error&&<div role="alert" className="alert error"><span>{error}</span><button onClick={()=>attempt(refresh)}>Reconnect</button><IconButton label="Dismiss error" onClick={()=>setError('')}><X size={16}/></IconButton></div>}{notice&&<div role="status" className="alert success"><CheckCircle2 size={17}/>{notice}</div>}
 
 {page===0&&<><div className="stats-grid"><Stat title="Gesture library" value={String(data.profiles.length).padStart(2,'0')} detail={`${activeCount} active mappings`} icon={<Hand/>} color="mint"/><Stat title="SafeIntent" value={running?'Active':'Standby'} detail={running?pretty(data.state):'Ready when you are'} icon={<ShieldCheck/>} color="purple"/><Stat title="Recognition accuracy" value={latest?`${Math.round(latest.personalized.accuracy*100)}%`:'—'} detail={latest?`${latest.sample_count} held-out examples`:'Adaptive recognition'} icon={<Activity/>} color="blue"/><Stat title="Action latency" value={latest?.events.median_latency_ms!=null?`${latest.events.median_latency_ms} ms`:'—'} detail={latest?'Median in replay timeline':'Fast verification'} icon={<CommandIcon/>} color="peach"/></div><div className="overview-grid"><div>{viewerPanel}<div className="card workflow"><div><span className="eyebrow">BUILT AROUND YOU</span><h3>A more natural way to interact.</h3><p>Enroll your gesture, choose a command, and let SafeIntent validate the rest.</p></div><Button secondary onClick={()=>navigate(1)}>Enroll a gesture <ArrowRight size={16}/></Button></div></div><div className="stack">{recognitionPanel}<div className="card"><div className="card-heading"><h3>Your gesture library</h3><button className="text-button" onClick={()=>navigate(1)}><Plus size={16}/>Add</button></div>{data.profiles.length?data.profiles.slice(0,3).map(p=><div className="mapping-mini" key={p.label}><div className="mapping-icon"><Hand size={18}/></div><div><strong>{p.label}</strong><span>{pretty(p.mapping.action)}</span></div><Badge tone={p.mapping.enabled?'green':'gray'}>{p.mapping.enabled?'Active':'Off'}</Badge></div>):<div className="empty compact"><Hand size={27}/><strong>Make it your own</strong><p>Your gesture library starts with you.</p><button className="text-button" onClick={()=>navigate(1)}>Create your first gesture <ArrowRight size={14}/></button></div>}</div><div className="assistant-card"><div className="spark-icon"><Sparkles size={19}/></div><h3>A little help getting set up.</h3><p>Describe what you want to do. Your setup assistant will handle the mapping.</p><button onClick={()=>navigate(4)}>Open setup assistant <ArrowUpRight size={16}/></button></div></div></div><div className="section-heading"><h3>Recent activity</h3><button className="text-button" onClick={()=>navigate(3)}>View event log <ArrowRight size={15}/></button></div><EventTable events={data.events.slice(0,4)}/></>}
 {page===1&&<GestureLab status={data} mode={mode} pose={pose} poseNames={poseNames} cameraActive={cameraActive} cameraStream={stream.current} onRefresh={refresh} onEnableCamera={enableCamera} onHalt={halt} getPoints={getPoints} onNavigate={navigate} setNotice={setNotice} setError={setError}/>}
 {page===2&&<><div className="live-grid"><div className="stack">{viewerPanel}{recognitionPanel}</div>{inputPanel}</div><div className="keyboard-strip"><CommandIcon size={17}/><strong>Keyboard alternative</strong><span>← → slices</span><span>+ − zoom</span><span>W A S D pan</span><span>R reset</span><span>Esc pause</span></div><div className="section-heading"><h3>Command history</h3><button className="text-button" onClick={()=>attempt(refresh)}>Refresh history</button></div><EventTable events={data.events.filter(e=>e.kind==='manual'||e.kind==='recognition').slice(0,8)}/></>}
 {page===3&&<><div className="section-heading"><div className="tabs">{['all','recognition','manual','configuration'].map(f=><button key={f} className={filter===f?'selected':''} onClick={()=>setFilter(f)}>{pretty(f)}</button>)}</div><div className="flex gap-2"><Button secondary onClick={()=>attempt(refresh)}>Refresh</Button><a className="button secondary" href="/api/export?format=json" download><Download size={16}/>Export log</a></div></div><EventTable events={data.events.filter(e=>filter==='all'||e.kind===filter)}/><div className="card mt-6"><h3>The SafeIntent pipeline</h3><div className="pipeline">{['Input','Landmarks','Classifier','Confidence','Dwell & stability','Allowlist','Execute'].map((s,i)=><span key={s}>{s}{i<6&&<ChevronRight size={15}/>}</span>)}</div><p className="muted small">State transitions: IDLE → ARMED → CANDIDATE → CONFIRMED → EXECUTED. Pause cancels pending candidates. Release your hand before repeating an action.</p></div></>}
 
 {page===4&&<div className="assistant-layout"><div className="card assistant-main"><div className="assistant-avatar"><Sparkles size={28}/></div><Badge tone="gray">Deterministic local parser</Badge><h2>Your gesture. Your command.</h2><p className="muted">Tell me how you’d like to interact with the viewer.<br/>I’ll suggest a supported mapping for you to review.</p><div className="suggestions">{['Zoom in','Move to the next slice','Reset view'].map(s=><button key={s} onClick={()=>setAssistantText(s)}>{s}<ArrowUpRight size={13}/></button>)}</div><label className="field-label" htmlFor="assistant-gesture">Choose an enrolled gesture</label><select id="assistant-gesture" value={selected} onChange={e=>{setSelected(e.target.value);setProposal(null);}}><option value="">Select a gesture</option>{data.profiles.map(p=><option key={p.label}>{p.label}</option>)}</select><label className="field-label" htmlFor="request">Describe the action</label><textarea id="request" value={assistantText} maxLength={500} onChange={e=>{setAssistantText(e.target.value);setProposal(null);}}/><Button disabled={!selected||busy} onClick={()=>attempt(async()=>{setBusy(true);setProposal(null);try{setProposal(await api<Mapping>('/assistant/propose','POST',{text:assistantText,gesture_label:selected}));}finally{setBusy(false);}})}><Sparkles size={16}/>Create proposed mapping</Button>{proposal&&<div className="proposal"><Badge tone="amber">Awaiting your confirmation</Badge><h3>{proposal.gesture_label} <ArrowRight size={18}/> {pretty(proposal.action)}</h3><pre>{JSON.stringify(proposal,null,2)}</pre><p className="small muted">Confirming saves this mapping disabled. Enable it after reviewing your library.</p><Button onClick={()=>attempt(async()=>{halt();setData(await api<Status>('/mappings','PUT',proposal));setProposal(null);setNotice('Mapping saved disabled. Enable it in Settings & privacy.');})}><Check size={17}/>Confirm & save mapping</Button></div>}</div><div className="stack"><div className="card"><ShieldCheck className="teal" size={28}/><h3>You’re always in control.</h3><p className="muted">The assistant can only propose commands from the viewer allowlist. It cannot execute actions, change safety settings, or access medical systems.</p><div className="supported-list">{commands.map(c=><span key={c}><Check size={13}/>{pretty(c)}</span>)}</div></div><div className="card"><h3>No API key needed</h3><p className="muted">Supported phrases are matched locally. Ambiguous requests and unsupported actions are rejected.</p><button className="text-button" onClick={()=>navigate(1)}>Enroll another gesture <ArrowRight size={15}/></button></div></div></div>}
 {page===5&&<div className="two-column"><div className="stack"><div className="card"><h3>Adaptive recognition</h3><p className="muted">Zoom requires at least 10% confidence. Each prediction displays its effective threshold, including per-gesture overrides.</p>{([{key:'threshold',name:'Confidence threshold',min:.1,max:1,step:.01},{key:'smoothing',name:'Landmark smoothing',min:0,max:.9,step:.05},{key:'dwell_ms',name:'Dwell duration (ms)',min:100,max:3000,step:50},{key:'cooldown_ms',name:'Cooldown (ms)',min:100,max:5000,step:100},{key:'sensitivity',name:'Activation sensitivity',min:.5,max:2,step:.05}] as const).map(s=><label className="slider-field" key={s.key}>{s.name}<strong>{settings[s.key]}</strong><input type="range" min={s.min} max={s.max} step={s.step} value={settings[s.key]} onChange={e=>setSettings({...settings,[s.key]:+e.target.value})}/></label>)}<Button onClick={()=>attempt(async()=>{halt();setData(await api<Status>('/settings','PUT',settings));setNotice('Recognition settings saved. Re-arm to continue.');})}>Save recognition settings</Button></div><div className="card"><h3>Gesture mappings & calibration</h3>{!data.profiles.length&&<p className="muted">Enroll a gesture to customize its mapping.</p>}{data.profiles.map(p=><MappingEditor key={p.label+JSON.stringify(p.mapping)} mapping={p.mapping} onSave={m=>attempt(async()=>{halt();setData(await api<Status>('/mappings','PUT',m));setNotice('Mapping saved. Re-arm to continue.');})}/>)}</div></div><div className="stack"><div className="card"><LockKeyhole size={28} className="teal"/><h3>Local by design</h3><p className="muted">Only hand landmark samples, settings, and evaluation logs are stored in your local SQLite database. Raw video is never recorded. Camera frames are processed in memory on localhost.</p><div className="privacy-status"><CheckCircle2 size={17}/>No external AI service</div><div className="privacy-status"><CheckCircle2 size={17}/>No automatic footage uploads</div><div className="privacy-status"><CheckCircle2 size={17}/>Keyboard fallback available</div><p className="muted small">Initial package and model downloads require internet. Offline operation has not been independently verified.</p></div><div className="card danger-zone"><h3>Delete local data</h3><p className="muted">Remove all gesture samples, mappings, settings, and evaluations. This cannot be undone.</p><Button secondary onClick={()=>{if(window.confirm('Delete all local gesture profiles, settings, and evaluation data?'))attempt(async()=>{halt();setData(await api<Status>('/data','DELETE'));setSettings(initialSettings);setRecognition(null);setSamples([]);setProposal(null);setNotice('All stored application data has been deleted.');});}}><Trash2 size={16}/>Delete all local data</Button></div></div></div>}
 <footer><span><ShieldCheck size={14}/>Research & demonstration only. Not a clinically validated medical device.</span><span>AirControl AI <span className="footer-dot">•</span> Vibethon 2026</span></footer></main></div>{running&&<button className="emergency-pause" onClick={halt}><Pause size={17}/>Pause recognition <kbd>Esc</kbd></button>}</div>;
}

function Stat({title,value,detail,icon,color}:{title:string;value:string;detail:string;icon:ReactNode;color:string}){return <div className="card stat"><div><span>{title}</span><div className={'stat-icon '+color}>{icon}</div></div><strong>{value}</strong><p>{detail}</p></div>}
function EventTable({events}:{events:Event[]}){return <div className="card event-table">{!events.length?<div className="empty compact"><Activity size={24}/><strong>A clear record of every decision</strong><p>Enroll or activate a gesture to see activity here.</p></div>:<div className="table-scroll"><table><thead><tr><th>Time</th><th>Event</th><th>Decision</th><th>Action / state</th></tr></thead><tbody>{events.map((e,i)=><tr key={e.time+i}><td>{new Date(e.time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}</td><td><span className={'event-dot '+(e.action?'accepted':'')}/>{e.label||pretty(e.kind)}{e.confidence!==undefined&&<small>{(e.confidence*100).toFixed(1)}% confidence</small>}</td><td>{e.reason}</td><td><Badge tone={e.action?'green':'gray'}>{e.action?pretty(e.action):e.state||pretty(e.kind)}</Badge></td></tr>)}</tbody></table></div>}</div>}
function HandDrawing({points}:{points:number[][]|null}){if(!points)return <div className="idle-hand"><Hand size={96} strokeWidth={.8}/><span>21 landmarks · 5 static poses</span></div>;return <svg viewBox="0 0 300 260" className="landmarks" role="img" aria-label="Synthetic hand landmark visualization">{[0,1,2,3,4].map(f=><polyline key={f} points={[0,...[1,2,3,4].map(j=>f*4+j)].map(i=>`${points[i][0]*300},${points[i][1]*260}`).join(' ')} fill="none" stroke="#5dc3a4" strokeWidth="2"/>)}{points.map((p,i)=><circle key={i} cx={p[0]*300} cy={p[1]*260} r={i%4===0?4:3} fill="#bcf4da"/>)}</svg>}
function MappingEditor({mapping,onSave}:{mapping:Mapping;onSave:(m:Mapping)=>void}){const [m,setM]=useState(mapping);return <div className="mapping-editor"><strong>{m.gesture_label}</strong><select aria-label={`Command for ${m.gesture_label}`} value={m.action} onChange={e=>setM({...m,action:e.target.value as Command})}>{commands.map(c=><option key={c} value={c}>{pretty(c)}</option>)}</select><label className="check-row"><input type="checkbox" checked={m.enabled} onChange={e=>setM({...m,enabled:e.target.checked})}/>Enable mapping</label><label className="field-label">Per-gesture threshold (blank uses global)<input type="number" min="0.5" max="1" step="0.01" value={m.threshold??''} onChange={e=>setM({...m,threshold:e.target.value===''?null:+e.target.value})}/></label><Button secondary onClick={()=>onSave(m)}>Confirm mapping</Button></div>}
