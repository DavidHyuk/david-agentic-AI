# Author: David Choi (bestshoot21@gmail.com)
"""Verify opt-in workbench chat across folding and room navigation."""
from pathlib import Path
import subprocess


def test_workbench_chat_folds_without_losing_drafts_and_resets_on_navigation():
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const elements = new Map(), document = {activeElement: null};
const $ = id => {
  if (!elements.has(id)) elements.set(id, {
    hidden: false, attributes: {}, classes: new Set(), value: '',
    contains(element) { return id === 'bench-character' && element === $('office-message'); },
    setAttribute(name, value) { this.attributes[name] = value; },
    focus() { document.activeElement = this; },
    classList: {toggle(name, active) {
      if (active) $(id).classes.add(name); else $(id).classes.delete(name);
    }},
  });
  return elements.get(id);
};
const context = {$, document, window: {}, setInterval: () => 0,
  view: () => {}, roomName: room => room};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
vm.runInContext('localWrite = () => {}; loadWorkbench = async () => {};', context);
function expectOpen(open) {
  assert.equal($('bench-character').hidden, !open);
  assert.equal($('bench-chat-toggle').attributes['aria-expanded'], String(open));
  assert.equal($('bench-chat-toggle').textContent, open ? 'LLM 채팅 숨기기' : 'LLM 채팅 열기');
  assert.equal($('workbench-view').classes.has('bench-chat-open'), open);
}
(async () => {
  for (const room of ['hq', 'papers', 'interview', 'coding', 'design', 'english', 'podcast', 'hq']) {
    await context.openWorkbench(room);
    expectOpen(false);
    $('office-message').value = '아직 보내지 않은 질문';
    $('bench-chat-toggle').onclick();
    expectOpen(true);
    assert.equal(document.activeElement, $('office-message'));
    $('bench-chat-toggle').onclick();
    expectOpen(false);
    assert.equal(document.activeElement, $('bench-chat-toggle'));
    $('bench-chat-toggle').onclick();
    expectOpen(true);
    assert.equal($('office-message').value, '아직 보내지 않은 질문');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run(['node', '-e', script, str(source)], capture_output=True,
                   text=True, check=True, timeout=10)
