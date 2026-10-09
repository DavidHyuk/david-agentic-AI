# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify private ChatGPT imports, branch selection, login isolation and errors."""
import json
from pathlib import Path
import zipfile
from types import SimpleNamespace
from contextlib import nullcontext

import pytest
import chatgpt_archive as archive


def prepare_daily_capture(tmp_path, monkeypatch, failure=None):
    project_id = 'g-p-' + 'a' * 32
    row = {'id': CHAT_ID, 'title': 'selected', 'url': f'https://chatgpt.com/g/{project_id}/c/{CHAT_ID}'}
    manifest = {'id': project_id, 'name': archive.DAILY_PROJECT, 'conversations': [row]}
    archive.save_json(tmp_path / 'browser-project.json', manifest)
    archive.save_json(tmp_path / 'browser-index.json', {'conversations': [row]})
    cache = {**row, 'messages': [{'role': 'user', 'text': 'old source'}]}
    archive.save_json(tmp_path / 'browser-chats' / (CHAT_ID + '.json'), cache)
    (tmp_path / 'project-rag.db').write_bytes(b'old index')
    calls = []
    monkeypatch.setattr(archive, 'project_browser', lambda *args: nullcontext())
    monkeypatch.setattr(archive, 'sync_project', lambda *args: {})
    def read(root, scrolls, refresh=False):
        calls.append(refresh)
        observed = [] if failure == 'shorter' else cache['messages'] + [{'role': 'assistant', 'text': 'new hint'}]
        archive.save_json(root / 'browser-chats' / (CHAT_ID + '.json'), {**cache, 'messages': observed})
        return {'failures': [{'id': CHAT_ID}] if failure == 'capture' else []}
    monkeypatch.setattr(archive, 'read_project', read)
    def rebuild(argv, **kwargs):
        root = Path(argv[argv.index('--data-dir') + 1])
        (root / 'project-rag.db').write_bytes(b'new index')
        return SimpleNamespace(returncode=1 if failure == 'vectors' else 0,
                               stdout=json.dumps({'conversation_count': 1, 'message_count': 2, 'chunk_count': 2}))
    monkeypatch.setattr(archive.subprocess, 'run', rebuild)
    return calls


def test_daily_sync_refreshes_sources_and_vectors_once_per_day(tmp_path, monkeypatch):
    calls = prepare_daily_capture(tmp_path, monkeypatch)
    result = archive.sync_daily(tmp_path, tmp_path, Path('/python'), archive.DAILY_PROJECT)
    assert result['status'] == 'ok' and calls == [True]
    assert (tmp_path / 'project-rag.db').read_bytes() == b'new index'
    assert len(archive.load_json(tmp_path / 'browser-chats' / (CHAT_ID + '.json'))['messages']) == 2
    assert archive.sync_daily(tmp_path, tmp_path, Path('/python'), archive.DAILY_PROJECT)['skipped']
    assert calls == [True]
    assert not list(tmp_path.glob('.daily-sync-*'))


@pytest.mark.parametrize('failure', ['capture', 'shorter', 'vectors'])
def test_failed_daily_capture_preserves_original_sources_and_index(tmp_path, monkeypatch, failure):
    prepare_daily_capture(tmp_path, monkeypatch, failure)
    cache = tmp_path / 'browser-chats' / (CHAT_ID + '.json')
    old = cache.read_bytes()
    with pytest.raises(archive.ArchiveError):
        archive.sync_daily(tmp_path, tmp_path, Path('/python'), archive.DAILY_PROJECT)
    assert cache.read_bytes() == old
    assert (tmp_path / 'project-rag.db').read_bytes() == b'old index'
    assert archive.load_json(tmp_path / 'daily-sync.json')['status'] == 'error'


def test_daily_sync_rejects_project_switch_and_existing_browser_lock(tmp_path, monkeypatch):
    prepare_daily_capture(tmp_path, monkeypatch)
    with pytest.raises(archive.ArchiveError, match='owner-selected'):
        archive.sync_daily(tmp_path, tmp_path, Path('/python'), 'Another project')
    with archive.locked(tmp_path, '.browser.lock'):
        with pytest.raises(archive.ArchiveError, match='Another ChatGPT operation'):
            archive.sync_daily(tmp_path, tmp_path, Path('/python'), archive.DAILY_PROJECT)


def test_publish_capture_rolls_back_on_partial_write_failure(tmp_path, monkeypatch):
    root, staging = tmp_path / 'live', tmp_path / 'staged'
    for folder, label in ((root, 'old'), (staging, 'new')):
        folder.mkdir()
        (folder / 'browser-chats').mkdir()
        for name in ('browser-project.json', 'browser-index.json', 'project-rag.db'):
            (folder / name).write_text(label)
    original = Path.replace
    def fail_index(self, target):
        if self == staging / 'project-rag.db':
            raise OSError('write failed')
        return original(self, target)
    monkeypatch.setattr(Path, 'replace', fail_index)
    with pytest.raises(OSError):
        archive.publish_project_capture(root, staging)
    assert all((root / name).read_text() == 'old' for name in
               ('browser-project.json', 'browser-index.json', 'project-rag.db'))


def test_partial_capture_merges_only_proven_ordered_overlap():
    rows = [{'role': 'user' if index % 2 == 0 else 'assistant', 'text': str(index)} for index in range(6)]
    old = {'messages': rows}
    result = archive.merge_partial_capture(old, {'messages': rows[1:4]})
    assert result['messages'] == rows and result['observed_message_count'] == 3
    new_message = {'role': 'user', 'text': 'new question'}
    result = archive.merge_partial_capture(old, {'messages': rows[-2:] + [new_message]})
    assert result['messages'] == rows + [new_message]
    with pytest.raises(archive.ArchiveError):
        archive.merge_partial_capture(old, {'messages': [new_message]})


def test_partial_capture_accepts_rendered_empty_lines_without_rewriting_source():
    code = 'Before\n\n```python\nif ready:\n    result = "a  b"\n```'
    rows = [{'role': 'user', 'text': 'Earlier question'},
            {'role': 'assistant', 'text': 'Earlier answer'},
            {'role': 'user', 'text': code},
            {'role': 'assistant', 'text': 'Original explanation'}]
    observed = [{'role': 'user', 'text': code.replace('\n', '\n\n\n\n')}, rows[3]]
    result = archive.merge_partial_capture({'messages': rows}, {'messages': observed})
    assert result['messages'] == rows
    assert result['messages'][2]['text'] == code
    assert result['retained_message_count'] == 2 and result['observed_message_count'] == 2


@pytest.mark.parametrize('replacement', ['result = "a b"', 'result = "a  b"', 'result  = "a  b"'])
def test_partial_capture_rejects_horizontal_code_changes(replacement):
    rows = [{'role': 'user', 'text': 'Earlier question'},
            {'role': 'assistant', 'text': 'Earlier answer'},
            {'role': 'user', 'text': 'if ready:\n    result = "a  b"'},
            {'role': 'assistant', 'text': 'Explanation'}]
    current = {'messages': [{'role': 'user', 'text': 'if ready:\n' + replacement}, rows[3]]}
    with pytest.raises(archive.ArchiveError, match='overlap'):
        archive.merge_partial_capture({'messages': rows}, current)


def test_partial_capture_appends_new_turn_after_blank_line_overlap():
    rows = [{'role': 'user', 'text': 'Old question'},
            {'role': 'assistant', 'text': 'Old answer'},
            {'role': 'user', 'text': 'Recent\nquestion'},
            {'role': 'assistant', 'text': 'Recent answer'}]
    question = {'role': 'user', 'text': 'Next actual question'}
    current = {'messages': [{'role': 'user', 'text': 'Recent\n\n\n\nquestion'}, rows[3], question]}
    result = archive.merge_partial_capture({'messages': rows}, current)
    assert result['messages'] == rows + [question]


def message(role, text, **extra):
    return {'author': {'role': role}, 'content': {'content_type': 'text', 'parts': [text]}, **extra}


def conversation(identifier='chat-1'):
    return {'id': identifier, 'title': '영어 ML interview', 'current_node': 'selected', 'mapping': {
        'root': {'parent': None, 'message': message('system', 'private system')},
        'user': {'parent': 'root', 'message': message('user', '영어 연습 Straße')},
        'other': {'parent': 'user', 'message': message('assistant', 'superseded branch')},
        'tool': {'parent': 'user', 'message': message('tool', 'private tool')},
        'hidden': {'parent': 'tool', 'message': message('assistant', 'hidden reasoning', metadata={
            'is_visually_hidden_from_conversation': True})},
        'selected': {'parent': 'hidden', 'message': message('assistant', 'Practice leadership')},
    }}


def export_file(tmp_path, records):
    path = tmp_path / 'export.json'
    path.write_text(json.dumps(records))
    return path


def test_active_branch_excludes_system_tools_hidden_content_and_alternatives():
    assert archive.conversation_messages(conversation()) == [
        {'role': 'user', 'text': '영어 연습 Straße', 'timestamp': None},
        {'role': 'assistant', 'text': 'Practice leadership', 'timestamp': None}]


def test_multimodal_messages_retain_text_without_asset_references():
    record = conversation()
    record['mapping']['selected']['message']['content'] = {
        'content_type': 'multimodal_text', 'parts': ['Discuss this', {'asset_pointer': 'private-image'}]}
    assert archive.conversation_messages(record)[-1]['text'] == 'Discuss this'


def test_assistant_analysis_channel_is_not_imported_as_visible_history():
    record = conversation()
    record['mapping']['selected']['message']['channel'] = 'analysis'
    assert [item['role'] for item in archive.conversation_messages(record)] == ['user']


@pytest.mark.parametrize('failure', ['cycle', 'missing', 'ambiguous'])
def test_invalid_branches_fail_without_guessing(failure):
    record = conversation()
    if failure == 'cycle':
        record['mapping']['root']['parent'] = 'selected'
    elif failure == 'missing':
        record['current_node'] = 'missing'
    else:
        record.pop('current_node')
    with pytest.raises(ValueError):
        archive.conversation_messages(record)


def test_unbranched_legacy_export_can_omit_current_node():
    record = conversation()
    record.pop('current_node')
    record['mapping'].pop('other')
    assert len(archive.conversation_messages(record)) == 2


def test_import_search_and_read_are_unicode_literal_and_owner_only(tmp_path):
    root = tmp_path / 'private'
    report = archive.import_export(export_file(tmp_path, [conversation()]), root)
    assert report['conversation_count'] == 1 and report['message_count'] == 2
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / 'archive.db').stat().st_mode & 0o777 == 0o600
    assert archive.search_archive(root, '영어 STRASSE', 20) == [{'id': 'chat-1', 'title': '영어 ML interview'}]
    assert archive.search_archive(root, "%' OR 1=1 --", 20) == []
    assert archive.show_conversation(root, 'chat-1')['messages'][0]['role'] == 'user'
    assert archive.archive_status(root)['imported_at'] == report['imported_at']


def test_reimport_replaces_snapshot_including_removed_chats(tmp_path):
    root = tmp_path / 'private'
    archive.import_export(export_file(tmp_path, [conversation('one'), conversation('two')]), root)
    archive.import_export(export_file(tmp_path, [conversation('two')]), root)
    assert archive.search_archive(root, '', 20) == [{'id': 'two', 'title': '영어 ML interview'}]
    with pytest.raises(ValueError, match='not found'):
        archive.show_conversation(root, 'one')


@pytest.mark.parametrize('bad', [[conversation(), conversation()], [{'id': 'broken', 'mapping': {}}], {}])
def test_malformed_import_preserves_previous_archive(tmp_path, bad):
    root = tmp_path / 'private'
    archive.import_export(export_file(tmp_path, [conversation()]), root)
    before = (root / 'archive.db').read_bytes()
    with pytest.raises(ValueError):
        archive.import_export(export_file(tmp_path, bad), root)
    assert (root / 'archive.db').read_bytes() == before


def test_zip_reads_only_conversation_json_without_extracting_other_files(tmp_path):
    path = tmp_path / 'export.zip'
    with zipfile.ZipFile(path, 'w') as bundle:
        bundle.writestr('conversations.json', json.dumps([conversation()]))
        bundle.writestr('../outside.txt', 'private account data')
        bundle.writestr('account.json', 'private account data')
    assert archive.import_export(path, tmp_path / 'private')['conversation_count'] == 1
    assert not (tmp_path / 'outside.txt').exists()
    assert not (tmp_path / 'private/account.json').exists()


def test_zip_uncompressed_size_is_bounded(tmp_path, monkeypatch):
    path = tmp_path / 'export.zip'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('conversations.json', ' ' * 4096)
    monkeypatch.setattr(archive, 'MAX_EXPORT_BYTES', 200)
    with pytest.raises(ValueError):
        archive.read_export(path)


def test_completed_browser_download_is_imported_once(tmp_path):
    folder = tmp_path / 'downloads'
    folder.mkdir()
    path = folder / 'export.zip'
    with zipfile.ZipFile(path, 'w') as bundle:
        bundle.writestr('conversations.json', json.dumps([conversation()]))
    seen = set()
    partial = Path(str(path) + '.crdownload')
    partial.touch()
    assert archive.import_downloads(tmp_path, seen) is None
    partial.unlink()
    assert archive.import_downloads(tmp_path, seen)['conversation_count'] == 1
    assert archive.import_downloads(tmp_path, seen) is None


def test_desktop_uses_own_profile_and_loopback_ports():
    commands = archive.desktop_commands(Path('/runtime'), Path('/private'), Path('/chrome'))
    assert '-nolisten' in commands[0]
    assert commands[1][commands[1].index('-listen') + 1] == '127.0.0.1'
    assert '127.0.0.1:18781' in commands[2]
    assert '--user-data-dir=/private/browser' in commands[3]
    assert '--remote-debugging-address=127.0.0.1' in commands[3]
    assert commands[3][-1] == 'https://chatgpt.com/'
    assert 'youtube.com' not in str(commands)


def test_status_never_returns_account_fields_or_session_credentials(tmp_path):
    archive.save_json(tmp_path / 'browser-status.json', {
        'browser_status': 'authenticated', 'email': 'private@example.com',
        'cookies': [{'value': 'private-token'}], 'export_link': 'https://private.example'})
    result = archive.archive_status(tmp_path)
    assert result['browser_status'] == 'authenticated'
    assert 'private' not in json.dumps(result)


def test_login_failure_cleans_up_status_and_hides_browser_exception(tmp_path, monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError('https://chatgpt.com/private?token=secret account@example.com')
    monkeypatch.setattr(archive, 'run_browser', fail)
    monkeypatch.setattr(archive.signal, 'signal', lambda *args: None)
    assert archive.main(['--data-dir', str(tmp_path), 'login']) == 1
    assert archive.load_json(tmp_path / 'browser-status.json')['browser_status'] == 'closed'
    output = capsys.readouterr().err
    assert 'RuntimeError' in output and 'secret' not in output and '@' not in output


def test_failed_read_does_not_create_empty_database(tmp_path):
    with pytest.raises(ValueError):
        archive.search_archive(tmp_path, '', 20)
    assert not (tmp_path / 'archive.db').exists()


@pytest.mark.parametrize('url', ['http://chatgpt.com/export', 'https://chatgpt.com.evil.test/export',
                              'https://chatgpt.com@evil.test/export', 'https://user:password@chatgpt.com/export',
                              'https://127.0.0.1/export', 'https://chatgpt.com:8443/export'])
def test_download_rejects_unrelated_origins_credentials_and_ports(url):
    with pytest.raises(ValueError):
        archive.validate_download_url(url)


def test_signed_official_download_url_is_accepted_without_rewriting():
    assert archive.validate_download_url('https://chatgpt.com/backend-api/content?token=private') is None


def test_login_recognizes_one_visible_profile_among_responsive_hidden_duplicates():
    visible = SimpleNamespace(count=lambda: 1, is_visible=lambda: True)
    duplicate = SimpleNamespace(count=lambda: 2, is_visible=lambda: False)
    absent = SimpleNamespace(count=lambda: 0, is_visible=lambda: False)
    def locator(selector):
        if 'Open profile menu' not in selector:
            return absent
        return visible if selector.endswith(':visible') else duplicate
    page = SimpleNamespace(url='https://chatgpt.com/', locator=locator)
    assert archive.profile_control(page) is visible
    assert archive.is_authenticated(page)


@pytest.mark.parametrize('outcome', ['confirmed', 'unconfirmed', 'verification'])
def test_export_uses_current_accessible_account_control_and_confirms_once(outcome):
    clicks = []
    class Control:
        def __init__(self, label, present=True):
            self.label, self.present = label, present
        def count(self):
            return int(self.present)
        def is_visible(self):
            return self.present
        def click(self, **kwargs):
            clicks.append(self.label)
            if self.label == 'Confirm export' and outcome == 'verification':
                page.url = 'https://auth.openai.com/verification'
        @property
        def first(self):
            return self
        def wait_for(self, **kwargs):
            if outcome != 'confirmed':
                raise TimeoutError('No success notice.')
    class Page:
        url = 'https://chatgpt.com/'
        def locator(self, selector):
            return Control('profile', 'Open profile menu' in selector and ':visible' in selector)
        def get_by_role(self, role, name):
            labels = {'menuitem': ['Settings'], 'button': ['Data controls', 'Export ChatGPT account data', 'Confirm export']}
            matching = [label for label in labels.get(role, []) if name.fullmatch(label)]
            return Control(matching[0] if matching else '', bool(matching))
        def wait_for_timeout(self, delay):
            pass
        def get_by_text(self, expression):
            return Control('success notice')
    page = Page()
    if outcome == 'confirmed':
        assert archive.request_export(page)
    elif outcome == 'verification':
        with pytest.raises(archive.ExportVerificationRequired):
            archive.request_export(page)
    else:
        with pytest.raises(TimeoutError):
            archive.request_export(page)
    assert clicks == ['profile', 'Settings', 'Data controls', 'Export ChatGPT account data', 'Confirm export']


def test_invalid_url_library_error_is_not_printed(tmp_path, monkeypatch, capsys):
    import io
    monkeypatch.setattr(archive.sys, 'stdin', io.StringIO('https://chatgpt.com:private-secret/export'))
    assert archive.main(['--data-dir', str(tmp_path), 'download']) == 1
    assert 'private-secret' not in capsys.readouterr().err


CHAT_ID = '12345678-1234-1234-1234-123456789abc'


def test_project_index_excludes_global_and_other_project_chats():
    project = 'g-p-' + 'a' * 32
    rows = [{'title': 'selected', 'url': f'/g/{project}/c/{CHAT_ID}'},
            {'title': 'global', 'url': f'/c/{CHAT_ID}'},
            {'title': 'other', 'url': f'/g/g-p-{"b" * 32}/c/{CHAT_ID}'}]
    assert [row['title'] for row in archive.project_conversations(rows, project)] == ['selected']
    with pytest.raises(archive.ArchiveError):
        archive.project_conversations(rows, '../../private')


def test_project_batch_skips_prior_reads_and_sanitizes_failures(tmp_path, monkeypatch):
    project = 'g-p-' + 'a' * 32
    other = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    rows = [{'id': identifier, 'title': 'selected', 'url': f'https://chatgpt.com/g/{project}/c/{identifier}'}
            for identifier in (CHAT_ID, other)]
    archive.save_json(tmp_path / 'browser-project.json', {'id': project, 'name': 'Career', 'conversations': rows})
    cache = {**rows[0], 'source': 'visible_browser', 'scroll_boundary_reached': True,
             'messages': [{'role': 'user', 'text': 'previous text'}]}
    archive.save_json(tmp_path / 'browser-chats' / (CHAT_ID + '.json'), cache)
    calls = []
    def fail(root, identifier, scrolls):
        calls.append(identifier)
        raise RuntimeError('private signed URL account@example.com')
    monkeypatch.setattr(archive, 'read_browser_conversation', fail)
    result = archive.read_project(tmp_path, 400)
    assert result['skipped'] == 1 and result['fetched'] == 0
    assert calls == [other] and result['failures'][0]['error'] == 'RuntimeError'
    assert archive.load_json(tmp_path / 'browser-chats' / (CHAT_ID + '.json')) == cache
    assert 'private' not in json.dumps(result)


def test_project_batch_rejects_manifest_containing_other_project(tmp_path, monkeypatch):
    project = 'g-p-' + 'a' * 32
    archive.save_json(tmp_path / 'browser-project.json', {'id': project, 'conversations': [
        {'title': 'wrong', 'url': f'/g/g-p-{"b" * 32}/c/{CHAT_ID}'}]})
    monkeypatch.setattr(archive, 'read_browser_conversation', lambda *args: pytest.fail('Must not read another project'))
    with pytest.raises(archive.ArchiveError):
        archive.read_project(tmp_path, 400)


def test_browser_scroll_merges_stable_messages_and_preserves_turn_order():
    observed = iter([
        [{'key': 'a', 'ordinal': 1, 'role': 'assistant', 'text': 'part'},
         {'key': 'u', 'ordinal': 0, 'role': 'user', 'text': 'question'}],
        [{'key': 'a', 'ordinal': 1, 'role': 'assistant', 'text': 'full answer'}]])
    moves = iter([True, False])
    messages = SimpleNamespace(count=lambda: 1, evaluate_all=lambda script: next(observed))
    scroll = SimpleNamespace(count=lambda: 1, evaluate=lambda script: None if 'flexDirection' in script else next(moves))
    scroll.first = scroll
    page = SimpleNamespace(locator=lambda selector: scroll if 'thread-scroll' in selector else messages,
                           wait_for_timeout=lambda value: None)
    result, boundary = archive.collect_browser_messages(page, 2)
    assert result == [{'role': 'user', 'text': 'question'}, {'role': 'assistant', 'text': 'full answer'}]
    assert boundary is True


def test_sidebar_keeps_only_titled_chatgpt_conversation_links_and_removes_duplicates():
    good = {'url': '/c/' + CHAT_ID + '?private=discard', 'title': '  영어 interview  '}
    rows = [good, good, {'url': 'https://evil.test/c/' + CHAT_ID, 'title': 'other'},
            {'url': '/g/project', 'title': 'project'}, {'url': '/c/' + CHAT_ID, 'title': ''},
            {'url': 'https://private@chatgpt.com/c/' + CHAT_ID, 'title': 'credentials'},
            {'url': '/c/../../private', 'title': 'traversal'}]
    assert archive.sidebar_conversations(rows) == [{
        'id': CHAT_ID, 'title': '영어 interview', 'url': 'https://chatgpt.com/c/' + CHAT_ID}]


def test_browser_index_search_does_not_claim_downloaded_content(tmp_path):
    archive.save_json(tmp_path / 'browser-index.json', {'conversations': [
        {'url': '/c/' + CHAT_ID, 'title': '영어 interview'}], 'captured_at': '2026-10-04T00:00:00+00:00'})
    result = archive.search_archive(tmp_path, '영어', 20)
    assert result[0]['id'] == CHAT_ID
    assert result[0]['content_available'] is False
    assert result[0]['source'] == 'visible_sidebar'
    assert archive.archive_status(tmp_path)['conversation_count'] == 0
    assert archive.archive_status(tmp_path)['sidebar_conversation_count'] == 1
    assert archive.archive_status(tmp_path)['sidebar_complete'] is False
    with pytest.raises(archive.ArchiveError, match='read-browser'):
        archive.show_conversation(tmp_path, CHAT_ID)


def test_search_and_show_can_use_one_cached_browser_chat_without_export(tmp_path):
    row = {'id': CHAT_ID, 'url': '/c/' + CHAT_ID, 'title': 'Title'}
    archive.save_json(tmp_path / 'browser-index.json', {'conversations': [row]})
    cached = {**row, 'source': 'visible_browser', 'complete': False,
              'messages': [{'role': 'user', 'text': 'Straße 영어 evidence'}]}
    archive.save_json(tmp_path / 'browser-chats' / (CHAT_ID + '.json'), cached)
    assert archive.search_archive(tmp_path, 'STRASSE', 20)[0]['content_available'] is True
    assert archive.show_conversation(tmp_path, CHAT_ID) == cached
    with pytest.raises(archive.ArchiveError):
        archive.show_conversation(tmp_path, '../../outside')


def test_nonindexed_browser_chat_is_rejected_before_launching_a_tab(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', SimpleNamespace(
        sync_playwright=lambda: pytest.fail('Unindexed URL must not be opened')))
    with pytest.raises(archive.ArchiveError, match='not in'):
        archive.read_browser_conversation(tmp_path, '../../private')


@pytest.mark.parametrize('redirect', ['https://auth.openai.com/verify',
                                   'https://chatgpt.com/c/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'])
def test_browser_redirect_never_saves_unrelated_conversation(tmp_path, monkeypatch, redirect):
    import sys
    archive.save_json(tmp_path / 'browser-index.json', {'conversations': [
        {'url': '/c/' + CHAT_ID, 'title': 'Selected'}]})
    cache = tmp_path / 'browser-chats' / (CHAT_ID + '.json')
    previous = {'messages': [{'role': 'user', 'text': 'previous verified text'}]}
    archive.save_json(cache, previous)
    closed = []
    locator = SimpleNamespace(count=lambda: 1, wait_for=lambda **kwargs: None,
                              evaluate_all=lambda script: pytest.fail('Unrelated text must not be read'))
    locator.first = locator
    page = SimpleNamespace(url=redirect, goto=lambda *args, **kwargs: None,
                           locator=lambda selector: locator, wait_for_timeout=lambda value: None,
                           close=lambda: closed.append(True))
    browser = SimpleNamespace(contexts=[SimpleNamespace(new_page=lambda: page)])
    class Playwright:
        chromium = SimpleNamespace(connect_over_cdp=lambda url: browser)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setitem(sys.modules, 'playwright.sync_api', SimpleNamespace(sync_playwright=Playwright))
    with pytest.raises(archive.ArchiveError, match='selected conversation'):
        archive.read_browser_conversation(tmp_path, CHAT_ID)
    assert archive.load_json(cache) == previous
    assert closed == [True]


def test_reconnect_closes_window_after_login_without_export_or_deleting_profile(tmp_path, monkeypatch):
    calls = []
    profile = tmp_path / 'browser'
    profile.mkdir()
    (profile / 'saved-profile').write_text('preserve')
    def run(runtime, data_dir, timeout, export, **options):
        calls.append((export, options))
        archive.save_json(data_dir / 'browser-status.json', {'browser_status': 'authenticated',
                                                         'authenticated_at': '2026-10-05T00:00:00+00:00'})
    monkeypatch.setattr(archive, 'run_browser', run)
    monkeypatch.setattr(archive.signal, 'signal', lambda *a: None)
    assert archive.main(['--data-dir', str(tmp_path), 'login', '--close-after-login']) == 0
    assert calls == [(False, {'close_after_login': True})]
    state = archive.load_json(tmp_path / 'browser-status.json')
    assert state['browser_status'] == 'closed' and state['authenticated_at']
    assert (profile / 'saved-profile').read_text() == 'preserve'
