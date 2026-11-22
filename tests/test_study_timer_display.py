# Author: David Choi (bestshoot21@gmail.com)
"""Check hour formatting and saved timer behavior using the real workbench JS."""
from pathlib import Path
import subprocess


def test_study_timer_shows_hours_and_preserves_pause_resume_and_reset():
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    script = r'''
const fs=require('fs'), vm=require('vm'), assert=require('node:assert/strict');
const elements={}, storage=new Map();
let now=1000000000, tick;
const context={$:id=>elements[id]||(elements[id]={}),window:{},
Date:{now:()=>now},clearInterval:()=>{},setInterval:callback=>{tick=callback;return 1;},
localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
vm.runInContext('bench.data={pending:[{id:"test-assignment"}]};',context);
const key='hermes-timer:test-assignment';
for(const [seconds,expected] of [[0,'00:00:00'],[59,'00:00:59'],[60,'00:01:00'],
  [3599,'00:59:59'],[3600,'01:00:00'],[10713,'02:58:33'],[90061,'25:01:01'],[360000,'100:00:00']]){
  context.localWrite(key,{elapsed:seconds*1000,started:null});
  context.wireTimer('test-assignment');
  assert.equal(elements['study-time'].textContent,expected);
  assert.equal(context.localRead(key).elapsed,seconds*1000);
}
context.localWrite(key,{elapsed:3599000,started:now-1000});
context.wireTimer('test-assignment');
assert.equal(elements['study-time'].textContent,'01:00:00');
elements['timer-toggle'].onclick();
assert.equal(context.localRead(key).started,null);
now+=10000;tick();
assert.equal(elements['study-time'].textContent,'01:00:00');
elements['timer-toggle'].onclick();
now+=1000;tick();
assert.equal(elements['study-time'].textContent,'01:00:01');
elements['timer-reset'].onclick();
assert.equal(elements['study-time'].textContent,'00:00:00');
assert.equal(context.localRead(key).elapsed,0);
assert.equal(context.localRead(key).started,null);
'''
    subprocess.run(['node', '-e', script, str(source)], capture_output=True,
                   text=True, check=True, timeout=10)
