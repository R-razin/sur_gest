/** Detect deliberate horizontal motion of an open hand across consecutive frames.
 * Camera landmarks are in image coordinates, not CSS-mirrored preview coordinates.
 * This is a temporal motion recognizer, separate from static KNN enrollment.
 */
export type Swipe = 'next_slice' | 'previous_slice';
type Point = {x:number; y:number; t:number};
export class SwipeDetector {
  private history:Point[]=[];
  private lastSwipe= -Infinity;
  moving=false;
  reset(){this.history=[];this.moving=false;}
  feed(landmarks:number[][] | null, now:number):Swipe|null {
    if(!landmarks || landmarks.length!==21){this.reset();return null;}
    // Track palm center, not a fingertip (which moves when the pose changes).
    const ids=[0,5,9,13,17];
    const x=ids.reduce((a,i)=>a+landmarks[i][0],0)/ids.length;
    const y=ids.reduce((a,i)=>a+landmarks[i][1],0)/ids.length;
    if(!Number.isFinite(x)||!Number.isFinite(y)){this.reset();return null;}
    if(this.history.length && now-this.history[this.history.length-1].t>350)this.reset();
    this.history.push({x,y,t:now});
    this.history=this.history.filter(p=>now-p.t<=1100).slice(-12);
    const recent=this.history.filter(p=>now-p.t<=420);
    this.moving=recent.length>=2 && Math.abs(x-recent[0].x)>0.065 && Math.abs(y-recent[0].y)<Math.abs(x-recent[0].x)*0.9;
    if(this.history.length<4 || now-this.lastSwipe<850)return null;
    const first=this.history[0], deltaX=x-first.x, deltaY=y-first.y, elapsed=now-first.t;
    // Ignore slow drifting, vertical movement, and one-frame jitter.
    if(elapsed<180 || elapsed>1100 || Math.abs(deltaX)<0.22 || Math.abs(deltaY)>Math.abs(deltaX)*0.65)return null;
    let direction=0, steps=0;
    for(let i=1;i<this.history.length;i++){
      const d=this.history[i].x-this.history[i-1].x;
      if(Math.abs(d)<0.012)continue;
      steps++;
      direction+=Math.sign(d);
    }
    if(steps<3 || Math.abs(direction)<Math.ceil(steps*0.6))return null;
    this.lastSwipe=now;
    this.reset();
    // Camera preview is mirrored for the user; right on screen corresponds to -X.
    return deltaX<0?'next_slice':'previous_slice';
  }
}
