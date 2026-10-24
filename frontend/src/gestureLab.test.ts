import {describe,it,expect} from 'vitest';
import {commands,pretty} from './types';

describe('Gesture Lab types and action registry',()=>{
  it('includes pause_control and all viewer commands in action registry',()=>{
    expect(commands).toContain('pause_control');
    expect(commands).toContain('zoom_in');
    expect(commands).toContain('zoom_out');
    expect(commands).toContain('next_slice');
    expect(commands).toContain('previous_slice');
    expect(commands).toContain('pan_left');
    expect(commands).toContain('pan_right');
    expect(commands).toContain('pan_up');
    expect(commands).toContain('pan_down');
    expect(commands).toContain('reset_view');
  });

  it('formats commands nicely for display',()=>{
    expect(pretty('pause_control')).toBe('Pause gesture control');
    expect(pretty('zoom_in')).toBe('Zoom in');
    expect(pretty('next_slice')).toBe('Next slice');
    expect(pretty('reset_view')).toBe('Reset view');
  });

  it('verifies valid gesture label regex requirements',()=>{
    const validRegex = /^[A-Za-z0-9 _-]{1,40}$/;
    expect(validRegex.test('My Zoom Gesture')).toBe(true);
    expect(validRegex.test('Pinch-Forward_1')).toBe(true);
    expect(validRegex.test('')).toBe(false);
    expect(validRegex.test('A'.repeat(41))).toBe(false);
    expect(validRegex.test('Invalid$Symbol!')).toBe(false);
  });
});
