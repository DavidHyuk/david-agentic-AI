# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Regression tests for reboot-safe, private Kakao skill URL refresh."""
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
import io

import pytest

import kakao_tunnel_url as tunnel


def test_origin_requires_connected_current_invocation():
    origin = 'https://current-tunnel.trycloudflare.com'
    assert tunnel.tunnel_origin(origin) is None
    assert tunnel.tunnel_origin(origin + '\nRegistered tunnel connection') == origin
    assert tunnel.tunnel_origin('https://evil.example\nRegistered tunnel connection') is None


def test_endpoint_validation_and_atomic_private_replace(tmp_path):
    env = tmp_path / '.env'
    env.write_text('UNRELATED=keep\nKAKAO_WEBHOOK_PATH="/kakao/private-path"\n')
    assert tunnel.endpoint_path(env) == '/kakao/private-path'
    dest = tmp_path / 'english/url.txt'
    assert tunnel.save_url(dest, 'https://current.example/kakao/private-path')
    assert dest.stat().st_mode & 0o777 == 0o600
    assert not tunnel.save_url(dest, dest.read_text().strip())
    assert tunnel.save_url(dest, 'https://new.example/kakao/private-path')
    assert list(dest.parent.iterdir()) == [dest]
    for invalid in ['', '/other/path', '/kakao/private?query', '/kakao/private/path']:
        env.write_text('KAKAO_WEBHOOK_PATH=' + invalid)
        with pytest.raises(ValueError):
            tunnel.endpoint_path(env)


@pytest.mark.parametrize('code,body,expected', [
    (400, {'version': '2.0', 'template': {'outputs': [{'simpleText': {'text': 'invalid'}}]}}, True),
    (404, {'version': '2.0', 'template': {'outputs': [{}]}}, False),
    (400, {'version': '2.0'}, False),
    (400, [], False),
])
def test_probe_requires_real_skill_response_without_lesson_payload(monkeypatch, code, body, expected):
    def open_request(request, timeout):
        assert request.data == b'{}'
        assert timeout == 4
        raise HTTPError(request.full_url, code, 'error', {}, io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(tunnel, 'urlopen', open_request)
    assert tunnel.endpoint_ready('https://current.example/kakao/private-path') is expected


def test_unreachable_probe_does_not_raise_secret_url(monkeypatch):
    def unreachable(*args, **kwargs):
        raise URLError('private url error')
    monkeypatch.setattr(tunnel, 'urlopen', unreachable)
    assert not tunnel.endpoint_ready('https://current.example/kakao/private-path')


def test_refresh_reads_current_invocation_and_preserves_existing_url_on_failure(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text('KAKAO_WEBHOOK_PATH=/kakao/private-path\n')
    dest = tmp_path / 'data/english/kakao-skill-url.txt'
    tunnel.save_url(dest, 'https://old.example/kakao/private-path')
    invocation = 'a' * 32
    calls = []
    def journal(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout='https://new.trycloudflare.com\nRegistered tunnel connection')
    monkeypatch.setattr(tunnel.subprocess, 'run', journal)
    monkeypatch.setattr(tunnel, 'endpoint_ready', lambda url: True)
    assert tunnel.refresh(tmp_path, invocation)
    assert f'_SYSTEMD_INVOCATION_ID={invocation}' in calls[0]
    assert dest.read_text().strip() == 'https://new.trycloudflare.com/kakao/private-path'
    with pytest.raises(ValueError, match='preserved'):
        tunnel.refresh(tmp_path, invocation, timeout=0)
    assert dest.read_text().strip() == 'https://new.trycloudflare.com/kakao/private-path'
    with pytest.raises(ValueError, match='invocation'):
        tunnel.refresh(tmp_path, '')


def test_startup_service_refreshes_private_url_after_every_tunnel_start():
    service = (Path(__file__).resolve().parents[1] / 'bootstrap/kakao-tunnel.service').read_text()
    assert 'ExecStartPost=/usr/bin/python3 %h/.hermes/scripts/kakao_tunnel_url.py' in service


def test_cli_failure_does_not_print_configuration_or_secret(monkeypatch, capsys):
    def fail(*args):
        raise ValueError('https://private.example/kakao/secret')
    monkeypatch.setattr(tunnel, 'refresh', fail)
    assert tunnel.main(['--home', '/nonexistent-test-home', '--invocation', 'b' * 32]) == 1
    assert 'secret' not in capsys.readouterr().err


def test_fixed_origin_validation():
    assert tunnel.fixed_origin('https://spark.example:10000/') == 'https://spark.example:10000'
    for value in ['http://spark.example', 'https://user:pass@spark.example',
                  'https://spark.example/kakao/secret', 'https://spark.example?secret=x',
                  'https://spark.example#fragment', 'https://spark.example:bad',
                  'https://spark.example\n']:
        with pytest.raises(ValueError):
            tunnel.fixed_origin(value)


def test_fixed_origin_preserves_url_if_unreachable_and_survives_next_run(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text('KAKAO_WEBHOOK_PATH=/kakao/private-path\n')
    dest = tmp_path / 'data/english/kakao-skill-url.txt'
    tunnel.save_url(dest, 'https://old.example/kakao/private-path')
    monkeypatch.setattr(tunnel, 'endpoint_ready', lambda url: False)
    with pytest.raises(ValueError, match='preserved'):
        tunnel.refresh_fixed(tmp_path, 'https://stable.example')
    assert dest.read_text().strip() == 'https://old.example/kakao/private-path'
    assert not dest.with_name('kakao-public-origin.txt').exists()
    monkeypatch.setattr(tunnel, 'endpoint_ready', lambda url: True)
    assert tunnel.refresh_fixed(tmp_path, 'https://stable.example')
    assert dest.read_text().strip() == 'https://stable.example/kakao/private-path'
    assert dest.with_name('kakao-public-origin.txt').stat().st_mode & 0o777 == 0o600
    # Future setup does not consult the temporary tunnel when fixed routing exists.
    monkeypatch.setattr(tunnel, 'refresh', lambda *args: pytest.fail('Quick Tunnel must not be used'))
    assert tunnel.main(['--home', str(tmp_path)]) == 0
