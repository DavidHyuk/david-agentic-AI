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


@pytest.mark.parametrize(('answer', 'has_code', 'has_summary'), [
    ('해시맵을 사용한 실제 구현 설명입니다.', True, True),
    ('class Solution:\n    def solve(self):\n        return "model rewrite"', True, True),
    ('', True, False),
    ('class Solution:\n    def solve(self):\n        return "invented answer"', False, True),
])
def test_solution_card_shows_exact_submission_without_another_expansion(answer, has_code, has_summary):
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    code = 'class Solution:\n    def solve(self):\n        # <img onerror=bad()>\n        return "actual submission"\n'
    row = {'slug': 'two-sum', 'title': 'Two Sum', 'language': 'Python3',
           'code': code if has_code else '', 'notes': []}
    if has_summary:
        row['summary'] = {'approach': '실제 구현 접근법', 'answer': answer,
                          'complexity': 'O(n)', 'hints': [], 'pitfalls': []}
    script = '''const fs=require('fs'), vm=require('vm');
const row=JSON.parse(fs.readFileSync(0,'utf8'));
const context={$:()=>({}),window:{},setInterval:()=>0,
esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
process.stdout.write(context.codingReviewCard({coding_reviews:{items:[row],ready_count:1}}));'''
    result = subprocess.run(['node', '-e', script, str(source)], input=json.dumps(row),
                            capture_output=True, text=True, check=True, timeout=10)
    parsed = CodeContent()
    parsed.feed(result.stdout)
    assert parsed.blocks == ([code] if has_code else [])
    assert parsed.tags.count('details') == 1  # Only the problem's outer expansion.
    assert 'img' not in parsed.tags
    assert 'model rewrite' not in result.stdout and 'invented answer' not in result.stdout
    if has_code:
        assert 'LeetCode에서 가져온 내 Accepted 제출 코드' in result.stdout
    else:
        assert 'Accepted 제출 코드 미확보' in result.stdout
    if has_summary and not answer.startswith('class'):
        assert answer in result.stdout


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


def test_manual_workbench_refresh_reloads_frontend_and_retains_room_url():
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    script = '''const fs=require('fs'), vm=require('vm');
const elements={};
const location={hash:'#workbench?room=coding',reload(){this.reloaded=true;}};
const context={$:id=>elements[id]||(elements[id]={}),window:{location},
setInterval:()=>0,api:()=>{throw new Error('Data refresh leaves the old renderer loaded');}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
elements['bench-reload'].onclick();
process.stdout.write(JSON.stringify(location));'''
    result = subprocess.run(['node', '-e', script, str(source)], capture_output=True,
                            text=True, check=True, timeout=10)
    assert json.loads(result.stdout) == {'hash': '#workbench?room=coding', 'reloaded': True}


def test_interview_script_is_visible_in_problem_expansion_and_escapes_all_text():
    from test_leetcode_review import SUMMARY
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    summary = SUMMARY | {'interview_script': SUMMARY['interview_script'] | {
        'walkthrough': 'I compare a < b. <img onerror=bad()> Then I move left.'},
        'interview_phrases': [{'english': 'Let me confirm <script>bad()</script>', 'korean': '<img>문제 확인'}]}
    row = {'code': 'return Counter(s) == Counter(t)', 'language': 'Python3', 'summary': summary}
    script = '''const fs=require('fs'), vm=require('vm');
const row=JSON.parse(fs.readFileSync(0,'utf8'));
const context={$:()=>({}),window:{},setInterval:()=>0,
esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
process.stdout.write(context.codingReviewBody(row,false));'''
    result = subprocess.run(['node', '-e', script, str(source)], input=json.dumps(row),
                            capture_output=True, text=True, check=True, timeout=10)
    parsed = CodeContent()
    parsed.feed(result.stdout)
    assert '영어 면접 스크립트 · 그대로 말하기' in result.stdout
    assert result.stdout.count('class="interview-speech"') == 6
    assert result.stdout.count('lang="en"') == 7
    assert '외워 쓸 표현' in result.stdout and '후속 질문 답변' in result.stdout
    assert 'img' not in parsed.tags and 'script' not in parsed.tags and 'details' not in parsed.tags
    assert 'a &lt; b' in result.stdout and '&lt;img&gt;문제 확인' in result.stdout
    assert summary['interview_script']['approach'] in result.stdout
