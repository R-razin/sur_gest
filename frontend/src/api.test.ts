import {describe,it,expect} from 'vitest';
import {cameraError} from './api';
describe('camera failure handling',()=>{
 it('explains denied permission and offers simulation',()=>expect(cameraError(new DOMException('Permission denied','NotAllowedError'))).toContain('switch to simulation'));
 it('preserves model/server failure details',()=>expect(cameraError(new Error('Hand Landmarker model is missing'))).toContain('model is missing'));
 it('handles unknown device errors',()=>expect(cameraError(null)).toContain('simulation'));
});
