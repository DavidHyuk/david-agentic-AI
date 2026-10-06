# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check rendered code readability and escaping without changing source text."""
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess

import pytest


class CodeContent(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks, self.tags, self.inside = [], [], False
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'code':
            self.blocks.append('')
            self.inside = True
    def handle_endtag(self, tag):
        if tag == 'code':
            self.inside = False
    def handle_data(self, data):
        if self.inside:
            self.blocks[-1] += data


@pytest.mark.parametrize(('text', 'language', 'expected'), [
    ('class Solution:\n    def solve(self):\n        # <script>ignore</script>\n        return "<img onerror=evil()>"\n', 'python3',
     ['class Solution:\n    def solve(self):\n        # <script>ignore</script>\n        return "<img onerror=evil()>"\n']),
    ('앞 설명\n```python\ndef f():\n    return "\\n"\n```\n뒤 설명', 'python3', ['def f():\n    return "\\n"\n']),
    ('```cpp\nif (a < b) return 1;\n```', 'cpp', ['if (a < b) return 1;\n']),
    ('두 포인터를 이동해 합을 비교합니다.\nO(n) 시간입니다.', 'python3', []),
])
def test_review_renderer_preserves_code_and_escapes_markup(text, language, expected):
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    script = '''const fs=require('fs'), vm=require('vm');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={$:()=>({}),window:{},setInterval:()=>0,
esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
process.stdout.write(context.reviewAnswer(data.text,data.language));'''
    result = subprocess.run(['node', '-e', script, str(source)], input=json.dumps({'text': text, 'language': language}),
                            capture_output=True, text=True, check=True, timeout=10)
    parsed = CodeContent()
    parsed.feed(result.stdout)
    assert parsed.blocks == expected
    assert 'script' not in parsed.tags and 'img' not in parsed.tags
    if language == 'python3' and expected:
        assert 'code-keyword' in result.stdout
    if not expected:
        assert 'completion-lesson' in result.stdout and 'pre' not in parsed.tags
