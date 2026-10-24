import {describe,it,expect} from 'vitest';
import {SwipeDetector, type Swipe} from './motion';
function hand(x:number,y=.5){return Array.from({length:21},()=>[x,y,0]);}
describe('camera swipe detection',()=>{
 it('detects a deliberate rightward swipe in the mirrored preview',()=>{const d=new SwipeDetector();let r:Swipe|null=null;for(let i=0;i<6;i++)r=d.feed(hand(.8-i*.055),i*90);expect(r).toBe('next_slice');});
 it('detects a deliberate leftward swipe',()=>{const d=new SwipeDetector();const events:Swipe[]=[];for(let i=0;i<6;i++){const r=d.feed(hand(.2+i*.055),i*90);if(r)events.push(r);}expect(events).toEqual(['previous_slice']);});
 it('ignores a steady pose',()=>{const d=new SwipeDetector();for(let i=0;i<10;i++)expect(d.feed(hand(.5),i*90)).toBeNull();});
 it('ignores vertical movement',()=>{const d=new SwipeDetector();for(let i=0;i<6;i++)expect(d.feed(hand(.5,.2+i*.055),i*90)).toBeNull();});
 it('does not repeatedly trigger while holding a position',()=>{const d=new SwipeDetector();let count=0;for(let i=0;i<6;i++)if(d.feed(hand(.8-i*.055),i*90))count++;for(let i=6;i<15;i++)if(d.feed(hand(.525),i*90))count++;expect(count).toBe(1);});
});
