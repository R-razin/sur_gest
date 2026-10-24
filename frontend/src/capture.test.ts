import {describe,it,expect} from 'vitest';
import {CaptureCoordinator} from './capture';

describe('one sequential camera producer',()=>{
 it('shares an in-flight frame between preview and recording',async()=>{
  const queue=new CaptureCoordinator<number>();let calls=0;let finish!:(n:number)=>void;
  const produce=()=>{calls++;return new Promise<number>(r=>{finish=r;});};
  const preview=queue.read(produce),record=queue.read(produce);
  expect(calls).toBe(1);finish(42);
  expect(await preview).toBe(42);expect(await record).toBe(42);
 });
 it('discards a late frame after pause or navigation',async()=>{
  const queue=new CaptureCoordinator<number>();let finish!:(n:number)=>void;
  const old=queue.read(()=>new Promise<number>(r=>{finish=r;}));
  const rejection=expect(old).rejects.toMatchObject({name:'AbortError'});
  queue.cancel();finish(1);await rejection;
  expect(await queue.read(async()=>2)).toBe(2);
 });
 it('waits for cancelled inference to settle before starting a new one',async()=>{
  const queue=new CaptureCoordinator<number>();let finish!:(n:number)=>void;let calls=0;
  const old=queue.read(()=>new Promise<number>(r=>{finish=r;})).catch(()=>null);
  queue.cancel();const current=queue.read(async()=>{calls++;return 9;});
  expect(calls).toBe(0);finish(1);await old;
  expect(await current).toBe(9);expect(calls).toBe(1);
 });
 it('aborts the underlying camera request',async()=>{
  const queue=new CaptureCoordinator<number>();let signal!:AbortSignal;
  const old=queue.read(s=>{signal=s;return new Promise((_,reject)=>s.addEventListener('abort',()=>reject(new DOMException('cancelled','AbortError'))));});
  const rejection=expect(old).rejects.toMatchObject({name:'AbortError'});
  queue.cancel();expect(signal.aborted).toBe(true);await rejection;
 });
});
