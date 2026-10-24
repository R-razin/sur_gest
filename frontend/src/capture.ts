/** One in-flight frame extraction shared by preview and capture consumers. */
export class CaptureCoordinator<T> {
  private generation = 0;
  private pending: {generation:number; promise:Promise<T>} | null = null;
  private controller:AbortController | null = null;
  cancel() { this.generation++; this.controller?.abort(); }
  async read(produce:(signal:AbortSignal)=>Promise<T>):Promise<T> {
    if(this.pending){
      if(this.pending.generation===this.generation)return this.pending.promise;
      await this.pending.promise.catch(()=>{});
      return this.read(produce);
    }
    const generation=this.generation;
    const controller=new AbortController(); this.controller=controller;
    const promise=produce(controller.signal).then(value=>{
      if(generation!==this.generation)throw new DOMException('Capture cancelled','AbortError');
      return value;
    });
    const pending={generation,promise}; this.pending=pending;
    try{return await promise;}finally{if(this.pending===pending)this.pending=null;}
  }
}
