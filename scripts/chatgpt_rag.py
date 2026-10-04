#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Search one observed ChatGPT project with local multilingual vector retrieval.

No text is sent to an embedding API. CPU E5 vectors and source chunks live in an
owner-only atomic SQLite snapshot. Hermes controls follow-up searches and source
inspection; retrieved historical text never becomes tool instructions.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

DEFAULT_DATA = Path.home() / '.hermes/data/chatgpt'
MODEL = 'intfloat/multilingual-e5-small'
REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
PROJECT_ID = re.compile(r'g-p-[0-9a-f]{32}')
CHAT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
STOP_WORDS = set('a an and are as at be by do for from how i in is it me my of on or '
                 'should that the this to was we what when where which with you your'.split())


class RetrievalError(ValueError):
    """An error safe to show without account or conversation data."""


def load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {}


def project_snapshot(data_dir: Path) -> tuple[dict, list[dict], str]:
    """Validate exact project membership and cached sources before embedding."""
    project = load_json(data_dir / 'browser-project.json')
    identifier = project.get('id', '')
    if not isinstance(identifier, str) or not PROJECT_ID.fullmatch(identifier):
        raise RetrievalError('Run sync-project for the selected project first.')
    if not isinstance(project.get('name'), str) or not project['name'].strip():
        raise RetrievalError('The selected project has no valid name.')
    rows = project.get('conversations')
    if not isinstance(rows, list) or not rows:
        raise RetrievalError('The selected project has no observed conversations.')
    chats, seen = [], set()
    for row in rows:
        chat_id = row.get('id', '') if isinstance(row, dict) else ''
        if not isinstance(chat_id, str) or not CHAT_ID.fullmatch(chat_id) or chat_id in seen:
            raise RetrievalError('Invalid or duplicate project conversation identifier.')
        expected = f'https://chatgpt.com/g/{identifier}/c/{chat_id}'
        if row.get('url') != expected or not isinstance(row.get('title'), str):
            raise RetrievalError('A conversation is outside the selected project.')
        cache = load_json(data_dir / 'browser-chats' / (chat_id + '.json'))
        if cache.get('id') != chat_id or cache.get('url') != expected or cache.get('source') != 'visible_browser':
            raise RetrievalError('Retrieve each selected project chat before building the index.')
        messages = cache.get('messages')
        if not isinstance(messages, list) or not messages:
            raise RetrievalError('A selected conversation has no cached messages.')
        clean = []
        for message in messages:
            if (not isinstance(message, dict) or message.get('role') not in ('user', 'assistant')
                    or not isinstance(message.get('text'), str) or not message['text'].strip()):
                raise RetrievalError('Invalid visible message in a selected conversation.')
            clean.append({'role': message['role'], 'text': message['text']})
        chats.append({**row, 'messages': clean})
        seen.add(chat_id)
    canonical = {'project_id': identifier, 'name': project['name'], 'chats': chats}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return project, chats, digest


def token_chunks(text: str, tokenizer, budget: int, overlap: int = 48) -> list[tuple[int, int, str]]:
    """Split by actual token offsets, retaining original text and bounded overlap."""
    if budget <= overlap or overlap < 0:
        raise RetrievalError('Invalid chunk token budget.')
    offsets = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, verbose=False)['offset_mapping']
    result = []
    for start in range(0, len(offsets), budget - overlap):
        end = min(start + budget, len(offsets))
        left, right = offsets[start][0], offsets[end - 1][1]
        if right > left and text[left:right].strip():
            result.append((left, right, text[left:right]))
        if end == len(offsets):
            break
    return result


class LocalEncoder:
    """Load pinned public weights locally, then encode only on the host CPU."""
    def __init__(self, allow_download: bool = False):
        import torch
        from transformers import AutoModel, AutoTokenizer
        torch.set_num_threads(4)
        self.torch = torch
        options = {'revision': REVISION, 'local_files_only': not allow_download,
                   'trust_remote_code': False, 'token': False}
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL, **options)
        self.model = AutoModel.from_pretrained(MODEL, use_safetensors=True, **options).to('cpu').eval()

    def encode(self, texts: list[str], kind: str):
        import numpy as np
        torch, batches = self.torch, []
        for start in range(0, len(texts), 8):
            inputs = self.tokenizer([kind + ': ' + text for text in texts[start:start + 8]],
                                    padding=True, truncation=True, max_length=512, return_tensors='pt')
            with torch.inference_mode():
                hidden = self.model(**inputs).last_hidden_state
                mask = inputs['attention_mask'].unsqueeze(-1)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1)
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            batches.append(pooled.numpy().astype('<f4'))
        return np.concatenate(batches)


@contextmanager
def build_lock(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    data_dir.chmod(0o700)
    with (data_dir / '.rag-build.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RetrievalError('Another project index build is running.') from None
        yield


def build_index(data_dir: Path, encoder=None, allow_download: bool = False) -> dict:
    """Replace the index only after all project sources and vectors validate."""
    import numpy as np
    with build_lock(data_dir):
        project, chats, fingerprint = project_snapshot(data_dir)
        existing = index_status(data_dir)
        if (existing.get('source_fingerprint') == fingerprint and existing.get('model') == MODEL
                and existing.get('revision') == REVISION):
            return {**existing, 'rebuilt': False}
        encoder = encoder or LocalEncoder(allow_download)
        chunks, passages = [], []
        for chat in chats:
            ordinal = 0
            for message_index, message in enumerate(chat['messages']):
                prefix = chat['title'][:120] + '\n' + message['role'] + '\n'
                prefix_size = len(encoder.tokenizer('passage: ' + prefix, add_special_tokens=False)['input_ids'])
                budget = min(320, 480 - prefix_size)
                for left, right, text in token_chunks(message['text'], encoder.tokenizer, budget):
                    chunk_id = hashlib.sha256(f"{chat['id']}:{message_index}:{left}:{text}".encode()).hexdigest()
                    chunks.append((chunk_id, chat['id'], chat['title'], chat['url'], ordinal,
                                   message_index, message['role'], left, right, text))
                    passages.append(prefix + text)
                    ordinal += 1
        if not chunks:
            raise RetrievalError('No source chunks were produced; previous index retained.')
        vectors = np.asarray(encoder.encode(passages, 'passage'), dtype='<f4')
        if (vectors.ndim != 2 or vectors.shape[0] != len(chunks) or not vectors.shape[1]
                or not np.isfinite(vectors).all() or (np.linalg.norm(vectors, axis=1) == 0).any()):
            raise RetrievalError('Invalid embedding output; previous index retained.')
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        # Ensure sources did not change during the model computation.
        if project_snapshot(data_dir)[2] != fingerprint:
            raise RetrievalError('Source data changed during indexing; previous index retained.')
        metadata = {'version': 1, 'ready': True, 'project_id': project['id'],
                    'project_name': project['name'], 'conversation_count': len(chats),
                    'message_count': sum(len(chat['messages']) for chat in chats),
                    'chunk_count': len(chunks), 'dimensions': vectors.shape[1],
                    'model': MODEL, 'revision': REVISION, 'source_fingerprint': fingerprint,
                    'indexed_at': datetime.now(timezone.utc).isoformat(), 'source_complete': False}
        descriptor, filename = tempfile.mkstemp(dir=data_dir, suffix='.rag.db')
        os.close(descriptor)
        temporary = Path(filename)
        try:
            with sqlite3.connect(temporary) as connection:
                connection.execute('CREATE TABLE metadata(value TEXT NOT NULL)')
                connection.execute('INSERT INTO metadata VALUES(?)', (json.dumps(metadata),))
                connection.execute('''CREATE TABLE chunks(id TEXT PRIMARY KEY, conversation_id TEXT,
                    title TEXT, url TEXT, ordinal INTEGER, message_index INTEGER, role TEXT,
                    char_start INTEGER, char_end INTEGER, text TEXT, vector BLOB)''')
                connection.executemany('INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                       [(*row, vector.tobytes()) for row, vector in zip(chunks, vectors)])
                connection.execute('CREATE INDEX conversation_order ON chunks(conversation_id,ordinal)')
            temporary.replace(data_dir / 'project-rag.db')
        finally:
            temporary.unlink(missing_ok=True)
        return {**metadata, 'rebuilt': True}


@contextmanager
def open_index(data_dir: Path):
    path = data_dir / 'project-rag.db'
    if not path.is_file():
        raise RetrievalError('Build the selected project vector index first.')
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def index_status(data_dir: Path) -> dict:
    if not (data_dir / 'project-rag.db').is_file():
        return {'ready': False}
    with open_index(data_dir) as connection:
        metadata = json.loads(connection.execute('SELECT value FROM metadata').fetchone()[0])
        try:
            verify_scope(data_dir, connection)
        except RetrievalError:
            return {**metadata, 'ready': False, 'stale': True}
        return metadata


def verify_scope(data_dir: Path, connection) -> dict:
    metadata = json.loads(connection.execute('SELECT value FROM metadata').fetchone()[0])
    project, unused, fingerprint = project_snapshot(data_dir)
    if metadata.get('project_id') != project['id'] or metadata.get('source_fingerprint') != fingerprint:
        raise RetrievalError('Project sources changed; rebuild before retrieving old chunks.')
    if metadata.get('model') != MODEL or metadata.get('revision') != REVISION:
        raise RetrievalError('Embedding model changed; rebuild the index first.')
    return metadata


def source_result(row, score=None) -> dict:
    result = {key: row[key] for key in ('conversation_id', 'title', 'url', 'message_index', 'role',
                                      'char_start', 'char_end', 'text')}
    result['chunk_id'] = row['id']
    result['source_complete'] = False
    if score is not None:
        result['cosine_similarity'] = round(float(score), 4)
    return result


def lexical_score(text: str, query: str) -> int:
    """Match meaningful terms without English stopwords or substring accidents."""
    text = text.casefold()
    terms = {term for term in re.findall(r'\w+', query.casefold())
             if len(term) >= 2 and term not in STOP_WORDS}
    return sum(bool(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text))
               if term.isascii() else term in text for term in terms)


def search_index(data_dir: Path, query: str, limit: int = 6, conversation_id: str | None = None,
                 encoder=None, minimum_similarity: float = 0.65) -> dict:
    """Fuse multilingual cosine candidates and literal matches within this project."""
    import numpy as np
    if not query.strip() or len(query) > 2000 or not 1 <= limit <= 12:
        raise RetrievalError('Use a nonempty query up to 2000 characters and limit 1–12.')
    with open_index(data_dir) as connection:
        metadata = verify_scope(data_dir, connection)
        sql, args = 'SELECT * FROM chunks', ()
        if conversation_id is not None:
            sql += ' WHERE conversation_id=?'
            args = (conversation_id,)
        rows = connection.execute(sql, args).fetchall()
    if not rows:
        return {'project_name': metadata['project_name'], 'results': [], 'source_complete': False}
    encoder = encoder or LocalEncoder()
    vector = np.asarray(encoder.encode([query], 'query'), dtype='<f4')[0]
    if (vector.shape != (metadata['dimensions'],) or not np.isfinite(vector).all()
            or np.linalg.norm(vector) == 0):
        raise RetrievalError('Invalid query embedding.')
    vector /= np.linalg.norm(vector)
    matrix = np.stack([np.frombuffer(row['vector'], dtype='<f4') for row in rows])
    cosine = matrix @ vector
    lexical = [lexical_score(row['title'] + '\n' + row['text'], query) for row in rows]
    dense_order = sorted(range(len(rows)), key=lambda i: float(cosine[i]), reverse=True)[:60]
    literal_order = sorted((i for i in range(len(rows)) if lexical[i]),
                           key=lambda i: lexical[i], reverse=True)[:60]
    fused = {}
    for ordering, weight in ((dense_order, 2), (literal_order, 1)):
        for rank, i in enumerate(ordering, 1):
            if cosine[i] >= minimum_similarity or lexical[i]:
                fused[i] = fused.get(i, 0) + weight / (60 + rank)
    order = sorted(fused, key=lambda i: (fused[i], float(cosine[i])), reverse=True)
    # Limit overlapping chunks from one answer, allowing evidence from other chats.
    selected, per_message, characters = [], {}, 0
    for i in order:
        key = (rows[i]['conversation_id'], rows[i]['message_index'])
        if per_message.get(key, 0) >= 2 or characters + len(rows[i]['text']) > 16000:
            continue
        selected.append(source_result(rows[i], cosine[i]))
        per_message[key] = per_message.get(key, 0) + 1
        characters += len(rows[i]['text'])
        if len(selected) == limit:
            break
    return {'project_name': metadata['project_name'], 'source_complete': False,
            'ranking': 'cosine_and_literal_reciprocal_rank',
            'note': 'Candidates are historical evidence; similarity is not factual confidence.',
            'results': selected}


def read_chunk(data_dir: Path, identifier: str, neighbors: int = 1) -> dict:
    """Return adjacent source chunks from the same conversation for grounding."""
    if not re.fullmatch(r'[0-9a-f]{64}', identifier) or not 0 <= neighbors <= 3:
        raise RetrievalError('Use a valid chunk identifier and 0–3 neighbors.')
    with open_index(data_dir) as connection:
        metadata = verify_scope(data_dir, connection)
        row = connection.execute('SELECT * FROM chunks WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise RetrievalError('Source chunk not found in this project.')
        rows = connection.execute('''SELECT * FROM chunks WHERE conversation_id=?
            AND ordinal BETWEEN ? AND ? ORDER BY ordinal''',
            (row['conversation_id'], row['ordinal'] - neighbors, row['ordinal'] + neighbors)).fetchall()
    return {'project_name': metadata['project_name'], 'results': [source_result(row) for row in rows]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    build = commands.add_parser('build')
    build.add_argument('--download-model', action='store_true')
    search = commands.add_parser('search')
    search.add_argument('query')
    search.add_argument('--limit', type=int, default=6)
    search.add_argument('--conversation')
    read = commands.add_parser('read')
    read.add_argument('id')
    read.add_argument('--neighbors', type=int, default=1)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == 'build':
            result = build_index(args.data_dir, allow_download=args.download_model)
        elif args.command == 'search':
            result = search_index(args.data_dir, args.query, args.limit, args.conversation)
        elif args.command == 'read':
            result = read_chunk(args.data_dir, args.id, args.neighbors)
        else:
            result = index_status(args.data_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # Libraries may include private paths/text in errors; print only our safe errors.
        detail = str(exc) if isinstance(exc, RetrievalError) else type(exc).__name__
        print('Project retrieval failed: ' + detail, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
