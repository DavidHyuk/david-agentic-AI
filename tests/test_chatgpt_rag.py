# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify project isolation, source preservation, vector retrieval and citations."""
import json
from types import SimpleNamespace

import pytest

import chatgpt_rag as rag

np = pytest.importorskip('numpy')
PROJECT = 'g-p-' + 'a' * 32
ONE = '11111111-1111-1111-1111-111111111111'
TWO = '22222222-2222-2222-2222-222222222222'


class Tokenizer:
    def __call__(self, text, **kwargs):
        return {'input_ids': list(range(len(text))),
                'offset_mapping': [(i, i + 1) for i in range(len(text))]}


class Encoder:
    tokenizer = Tokenizer()

    def encode(self, texts, kind):
        return np.array([[1., 0.] if ('Staff' in t or 'promotion' in t) else [0., 1.]
                         for t in texts], dtype='<f4')


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.fixture
def sources(tmp_path):
    rows = []
    for chat_id, title, text in [(ONE, 'Career', 'Staff engineer scope and ownership'),
                                 (TWO, 'Memory', 'Semantic versus episodic agent memory')]:
        row = {'id': chat_id, 'title': title, 'url': f'https://chatgpt.com/g/{PROJECT}/c/{chat_id}'}
        rows.append(row)
        write_json(tmp_path / 'browser-chats' / (chat_id + '.json'),
                   {**row, 'source': 'visible_browser', 'messages': [
                       {'role': 'user', 'text': 'My question'}, {'role': 'assistant', 'text': text}]})
    write_json(tmp_path / 'browser-project.json', {'id': PROJECT, 'name': 'Career 2027', 'conversations': rows})
    return tmp_path


def test_token_chunks_preserve_original_unicode_and_overlap():
    text = '가나다라마바사아자차카타파하'
    chunks = rag.token_chunks(text, Tokenizer(), 6, 2)
    assert chunks[0][0] == 0 and chunks[-1][1] == len(text)
    assert all(text[left:right] == part for left, right, part in chunks)
    assert all(chunks[i + 1][0] < chunks[i][1] for i in range(len(chunks) - 1))
    assert set().union(*(set(range(left, right)) for left, right, part in chunks)) == set(range(len(text)))


def test_lexical_retrieval_ignores_stopwords_and_matches_english_word_boundaries():
    assert rag.lexical_score('chair formal should coding', 'How should I prepare for AI?') == 0
    assert rag.lexical_score('AI 기반 리트코드 면접 준비', 'AI 리트코드 면접') == 3


@pytest.mark.parametrize('change', ['wrong_project', 'traversal', 'wrong_cached_url', 'hidden_role'])
def test_project_source_validation_fails_closed(sources, change):
    manifest = rag.load_json(sources / 'browser-project.json')
    cache_path = sources / 'browser-chats' / (ONE + '.json')
    cached = rag.load_json(cache_path)
    if change == 'wrong_project':
        manifest['conversations'][0]['url'] = f'https://chatgpt.com/g/g-p-{"b" * 32}/c/{ONE}'
    elif change == 'traversal':
        manifest['conversations'][0]['id'] = '../../outside'
    elif change == 'wrong_cached_url':
        cached['url'] = 'https://evil.test/private'
    else:
        cached['messages'][0]['role'] = 'system'
    write_json(sources / 'browser-project.json', manifest)
    write_json(cache_path, cached)
    with pytest.raises(rag.RetrievalError):
        rag.project_snapshot(sources)


def test_build_is_private_atomic_and_idempotent_and_ignores_unselected_chats(sources):
    write_json(sources / 'browser-chats/outside.json', {'messages': [{'text': 'private other project'}]})
    report = rag.build_index(sources, Encoder())
    assert report['conversation_count'] == 2 and report['message_count'] == 4
    assert report['chunk_count'] == 4 and report['source_complete'] is False
    assert (sources / 'project-rag.db').stat().st_mode & 0o077 == 0
    assert sources.stat().st_mode & 0o077 == 0
    result = rag.build_index(sources, SimpleNamespace(encode=lambda *args: pytest.fail('No repeat embedding')))
    assert result['rebuilt'] is False


def test_semantic_search_without_literal_overlap_returns_cited_source_and_neighbors(sources):
    rag.build_index(sources, Encoder())
    result = rag.search_index(sources, 'promotion', encoder=Encoder())
    assert len(result['results']) == 1
    hit = result['results'][0]
    assert hit['conversation_id'] == ONE
    assert 'promotion' not in hit['text']
    assert hit['url'] == f'https://chatgpt.com/g/{PROJECT}/c/{ONE}'
    assert hit['role'] == 'assistant' and hit['message_index'] == 1
    neighboring = rag.read_chunk(sources, hit['chunk_id'])['results']
    assert [row['role'] for row in neighboring] == ['user', 'assistant']
    assert all(row['conversation_id'] == ONE for row in neighboring)
    assert rag.search_index(sources, 'promotion', conversation_id=TWO, encoder=Encoder())['results'] == []


def test_low_similarity_returns_no_candidate_without_literal_evidence(sources):
    rag.build_index(sources, Encoder())
    encoder = SimpleNamespace(encode=lambda *args: np.array([[-1., 0.]], dtype='<f4'))
    assert rag.search_index(sources, 'unrelated', encoder=encoder)['results'] == []


def test_changed_sources_require_rebuild_and_failed_embeddings_keep_previous_db(sources):
    rag.build_index(sources, Encoder())
    previous = (sources / 'project-rag.db').read_bytes()
    path = sources / 'browser-chats' / (ONE + '.json')
    cached = rag.load_json(path)
    cached['messages'][0]['text'] += ' changed'
    write_json(path, cached)
    assert rag.index_status(sources)['ready'] is False
    assert rag.index_status(sources)['stale'] is True
    with pytest.raises(rag.RetrievalError, match='rebuild'):
        rag.search_index(sources, 'promotion', encoder=Encoder())
    bad = SimpleNamespace(tokenizer=Tokenizer(), encode=lambda texts, kind: np.full((len(texts), 2), np.nan))
    with pytest.raises(rag.RetrievalError, match='embedding'):
        rag.build_index(sources, bad)
    assert (sources / 'project-rag.db').read_bytes() == previous


def test_missing_project_cache_never_falls_back_to_account_archive(sources):
    (sources / 'browser-chats' / (ONE + '.json')).unlink()
    with pytest.raises(rag.RetrievalError, match='Retrieve each'):
        rag.build_index(sources, Encoder())


def test_library_errors_do_not_print_private_chat_content(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError('private conversation account@example.com')
    monkeypatch.setattr(rag, 'search_index', fail)
    assert rag.main(['search', 'promotion']) == 1
    output = capsys.readouterr().err
    assert 'RuntimeError' in output and 'private' not in output
