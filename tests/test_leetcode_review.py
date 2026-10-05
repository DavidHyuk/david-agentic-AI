# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify source fidelity, cache invalidation and background review boundaries."""
import fcntl
import json
from pathlib import Path

import pytest

import leetcode_review as review


SUMMARY = {'approach': '빈도표를 비교한다.', 'answer': '저장된 구현 설명',
           'complexity': 'O(n)', 'hints': ['같은 문자의 횟수는?'], 'pitfalls': ['빈 입력']}


@pytest.fixture
def home(tmp_path):
    root = tmp_path / 'data/interview'
    root.mkdir(parents=True)
    (root / 'leetcode_history.json').write_text(json.dumps({
        'version': 1, 'username': 'david', 'session': 'NEVER INCLUDE',
        'recent_accepted': [{'slug': 'valid-anagram', 'title': 'Valid Anagram',
                             'accepted_at': '2026-10-04T00:00:00+00:00'},
                            {'slug': 'reverse-string', 'title': 'Reverse String'}],
        'accepted_solutions': [{'slug': 'valid-anagram', 'title': 'Valid Anagram',
                                'accepted_at': '2026-10-04T00:00:00+00:00',
                                'language': 'Python3', 'code': 'return Counter(s) == Counter(t)'}]}))
    (root / 'coach_state.json').write_text(json.dumps({
        'coding': [], 'assignments': {'new': {'item_id': 'unsolved-problem'}},
        'external_coding': {'valid-anagram': {'item_id': 'valid-anagram',
            'date': '2026-10-04', 'lesson': '빈도 비교', 'hint_notes': '정렬 없이 세기',
            'source': {'url': 'https://chatgpt.com/c/example'}}}}))
    return tmp_path


def test_cached_reviews_use_actual_source_and_never_modify_progress(home):
    history, state, cache = review.paths(home)
    before = history.read_bytes(), state.read_bytes()
    calls = []
    def generator(source, model_home):
        calls.append(source)
        assert model_home == home
        assert source['code'] == 'return Counter(s) == Counter(t)'
        assert source['notes'][0]['hint_notes'] == '정렬 없이 세기'
        assert 'NEVER INCLUDE' not in json.dumps(source)
        return SUMMARY
    assert review.prepare(home, generator=generator)['prepared'] == 1
    assert review.prepare(home, generator=generator)['prepared'] == 0
    assert len(calls) == 1
    data = review.list_reviews(home)
    assert data['ready_count'] == 1
    assert {r['slug'] for r in data['items']} == {'valid-anagram', 'reverse-string'}
    assert next(r for r in data['items'] if r['slug'] == 'reverse-string')['status'] == 'pending'
    assert (history.read_bytes(), state.read_bytes()) == before
    assert cache.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('change', ['code', 'notes', 'username'])
def test_source_changes_hide_stale_summary_until_rebuilt(home, change):
    review.prepare(home, generator=lambda *_: SUMMARY)
    history, state, _ = review.paths(home)
    path = state if change == 'notes' else history
    data = json.loads(path.read_text())
    if change == 'code':
        data['accepted_solutions'][0]['code'] = 'return sorted(s) == sorted(t)'
    elif change == 'notes':
        data['external_coding']['valid-anagram']['lesson'] = '새로운 실제 배움'
    else:
        data['username'] = 'another-account'
    path.write_text(json.dumps(data))
    assert review.list_reviews(home)['ready_count'] == 0
    assert all('summary' not in r for r in review.list_reviews(home)['items'])
    assert review.prepare(home, generator=lambda *_: SUMMARY)['prepared'] == 1


def test_newer_accepted_event_does_not_show_old_code(home):
    history = review.paths(home)[0]
    data = json.loads(history.read_text())
    data['recent_accepted'][0]['accepted_at'] = '2026-10-05T00:00:00+00:00'
    history.write_text(json.dumps(data))
    source = review.list_reviews(home)['items'][0]
    assert not source.get('code')
    assert source['accepted_at'] == '2026-10-05T00:00:00+00:00'


def test_partial_failure_retains_saved_reviews_and_stops_batch(home):
    state = review.paths(home)[1]
    data = json.loads(state.read_text())
    data['coding'] = [{'item_id': 'two-sum', 'date': '2026-10-03', 'lesson': '해시맵'}]
    state.write_text(json.dumps(data))
    calls = []
    def generator(source, _):
        calls.append(source['slug'])
        if len(calls) == 2:
            raise OSError('Model unavailable')
        return SUMMARY
    assert review.prepare(home, generator=generator) == {'status': 'error', 'prepared': 1, 'failed': 1}
    assert review.list_reviews(home)['ready_count'] == 1
    assert len(calls) == 2


def test_preparation_lock_prevents_duplicate_model_requests(home):
    lock = review.paths(home)[2].parent / '.leetcode-reviews.lock'
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        result = review.prepare(home, generator=lambda *_: pytest.fail('duplicate request'))
    assert result['status'] == 'busy'


def test_learning_only_review_keeps_implementation_and_complexity_unknown(home):
    history = review.paths(home)[0]
    data = json.loads(history.read_text())
    data['accepted_solutions'] = []
    history.write_text(json.dumps(data))
    review.prepare(home, generator=lambda *_: SUMMARY)
    row = review.list_reviews(home)['items'][0]
    assert not row.get('code')
    assert row['summary']['answer'].startswith('실제 Accepted 코드 미확보')
    assert '확인하지 못했습니다' in row['summary']['complexity']
    assert row['notes'][0]['hint_notes'] == '정렬 없이 세기'


def test_local_model_request_marks_background_and_omits_credentials(home, monkeypatch):
    import io
    (home / 'config.yaml').write_text('model:\n  provider: custom:local\nproviders:\n  local:\n    base_url: http://localhost:8003/v1\n    model: test-model\n')
    requests = []
    def request(req, **kwargs):
        requests.append(req)
        assert kwargs['timeout'] == 240
        return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(SUMMARY)}}]}).encode())
    monkeypatch.setattr(review, 'urlopen', request)
    assert review.summarize(review.load_sources(home)[1][0], home) == SUMMARY
    assert requests[0].get_header('X-local-workload') == 'background'
    assert 'NEVER INCLUDE' not in requests[0].data.decode()
    config = home / 'config.yaml'
    config.write_text(config.read_text().replace('http://localhost:8003', 'https://external.example'))
    with pytest.raises(ValueError, match='local model'):
        review.summarize({}, home)
    assert len(requests) == 1


@pytest.mark.parametrize('value', [None, SUMMARY | {'answer': ''}, SUMMARY | {'hints': ['a'] * 9},
                                 SUMMARY | {'pitfalls': [3]}])
def test_invalid_model_output_is_not_persisted(home, value):
    assert review.prepare(home, generator=lambda *_: value)['failed'] == 1
    assert not review.paths(home)[2].exists()
