export async function api<T>(path:string,method='GET',body?:unknown,signal?:AbortSignal):Promise<T>{
  const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(15000)]):AbortSignal.timeout(15000)});
  if(!r.ok){const data=await r.json().catch(()=>({detail:'Backend is unavailable.'}));throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
  return r.json();
}
export function cameraError(error:unknown){return error instanceof DOMException&&error.name==='NotAllowedError'?'Camera permission was denied. Allow camera access or switch to simulation.':error instanceof Error?error.message:'Camera unavailable. Use simulation mode.';}
