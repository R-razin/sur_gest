import {useEffect,useRef} from 'react';
import type {ViewerState} from './types';

// Procedural axial phantom. Original mathematical artwork, no patient data.
export function Phantom({view}:{view:ViewerState}){
 const ref=useRef<HTMLCanvasElement>(null);
 useEffect(()=>{
  const ctx=ref.current?.getContext('2d');if(!ctx)return;
  const n=440,img=ctx.createImageData(n,n),z=((view.slice%32)-15.5)/24,series=Math.floor(view.slice/32);
  for(let j=0;j<n;j++)for(let i=0;i<n;i++){
   const x=(i-n/2)/(n*.355),y=(j-n/2)/(n*.415),r=Math.sqrt(x*x+y*y),a=Math.atan2(y,x);
   const edge=.94-.16*z*z+.015*Math.sin(a*(5+series)),noise=Math.sin(i*127.1+j*311.7+view.slice*7)*43758.5453;
   let v=4+(noise-Math.floor(noise))*5;
   if(r<edge){v=50+8*Math.sin(x*12+y*4);if(r>edge-.055)v=185+30*Math.cos(r*80);else if(r>edge-.09)v=38;else{
    const folds=Math.sin((23+series*5)*r+4*Math.sin((7+series)*a)+2*Math.sin(y*(13+series*3))+z*5);
    v=112+19*Math.sin(x*(8+series*2))*Math.cos(y*(9+series))+17*folds+(noise-Math.floor(noise))*17;
    if(folds>.79&&r>.44)v-=45;
    const l=((Math.abs(x)-.16)/.115)**2+((y+.02-z*.1)/.25)**2;
    if(l<1)v=25+18*l;
     // Four distinct synthetic research series, each changing through 32 axial levels.
     if(series===1){
       const ventricles=((Math.abs(x)-.22)/.13)**2+((y-.03-z*.12)/.19)**2;
       if(ventricles<1)v=24+12*ventricles;
       const midline=(x/.045)**2+((y+.26)/.31)**2;
       if(midline<1)v=55+10*midline;
     } else if(series===2){
       const lobe1=((x+.31)/.31)**2+((y+.12-z*.11)/.33)**2;
       const lobe2=((x-.31)/.31)**2+((y+.12+z*.11)/.33)**2;
       if(lobe1<1||lobe2<1)v=135+13*Math.cos(15*x+20*y);
       const sinuses=((x)/.25)**2+((y-.36)/.14)**2;
       if(sinuses<1)v=18;
     }
    if(series===3){
       const cavity=((x+.08)/.36)**2+((y-.14-z*.12)/.20)**2;
       const rim=((x-.24)/.25)**2+((y+.29)/.27)**2;
       if(cavity<1)v=25+18*cavity;
       if(rim<1)v=168+16*Math.cos(18*r+z*4);
       if(Math.abs(x+.22)<.055&&y<-.10)v=38;
     }
    if(Math.abs(x)<.012&&y<.6)v=40;
    if((x/.25)**2+((y-.50)/.15)**2<1)v=90+18*Math.sin(x*80);
   }}
   const p=(j*n+i)*4;img.data[p]=img.data[p+1]=img.data[p+2]=v;img.data[p+3]=255;
  }
  ctx.putImageData(img,0,0);
 },[view.slice]);
 return <canvas ref={ref} width={440} height={440} role="img" aria-label={`Synthetic axial phantom, slice ${view.slice+1} of 128`} style={{transform:`translate(${view.x}px,${view.y}px) scale(${view.zoom})`}}/>;
}
