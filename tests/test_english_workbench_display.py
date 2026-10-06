# Author: David Choi (bestshoot21@gmail.com)
"""Verify bilingual correction notes and retained caption practice in workbenches."""
import json
from pathlib import Path
import subprocess

import pytest


def render(function, data):
    source = Path(__file__).resolve().parents[1] / 'browser/observatory/workbench.js'
    script = '''const fs=require('fs'), vm=require('vm');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const context={$:()=>({}),window:{},setInterval:()=>0,
esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
process.stdout.write(context[process.argv[2]](data));'''
    return subprocess.run(['node', '-e', script, str(source), function], input=json.dumps(data),
                          capture_output=True, text=True, check=True, timeout=10).stdout


def test_ellie_shows_korean_before_english_reference_and_keeps_grading_buttons():
    html = render('englishDesk', {'due_count': 1, 'total_cards': 1, 'due': [{
        'wrong': 'I go yesterday.', 'correct': 'I went yesterday.', 'box': 1, 'due': '2026-10-06',
        'note': '과거 일이므로 went를 씁니다. <img>', 'note_en': 'Use the past tense. <script>'}]})
    assert html.index('과거 일이므로') < html.index('영어 참고')
    assert '&lt;img&gt;' in html and '&lt;script&gt;' in html
    assert '<img>' not in html and '<script>' not in html
    assert 'data-result="correct"' in html and 'data-result="wrong"' in html
    assert 'I went yesterday.' in html


@pytest.mark.parametrize('current', [False, True])
def test_rina_shows_dated_source_sentences_without_duplicate_long_quotes(current):
    long = {'source_quote': 'Long source quote <img>.', 'timestamp': '09:25', 'word_count': 23,
            'url': 'https://www.youtube.com/watch?v=abcdefghijk&t=565', 'patterns': []}
    short = {'source_quote': 'Short source quote.', 'timestamp': '01:00', 'word_count': 9, 'patterns': []}
    practice = {'status': 'ready', 'lesson_date': '2026-10-05', 'title': 'Saved source',
                'sentences': [long], 'weakness_candidates': [long, short]}
    html = render('podcastDesk', {'watch_history': {},
        'long_sentence_practice': practice if current else {'status': 'unavailable', 'reason': 'No current captions.'},
        'saved_sentence_practice': None if current else practice})
    assert ('오늘의 문장 연습' if current else '최신 저장 문장 연습') in html
    assert '2026-10-05' in html
    assert html.count('Long source quote &lt;img&gt;.') == 1
    assert 'Short source quote.' in html and '짧은 문장·표현 연습' in html
    assert '<img>' not in html and '이 문장 듣기' in html


def test_rina_shows_empty_state_and_weekend_source_sentences():
    empty = render('podcastDesk', {'watch_history': {}})
    assert '저장된 대본 연습 문장이 아직 없습니다.' in empty
    weekend = render('podcastDesk', {'watch_history': {}, 'podcast_review': {
        'status': 'ready', 'week_start': '2026-09-28', 'week_end': '2026-10-02', 'episodes': [{
            'title': 'Weekday source', 'source_dates': ['2026-10-01'],
            'sentences': [{'source_quote': 'A weekend review quote.', 'patterns': []}]}]}})
    assert 'A weekend review quote.' in weekend
