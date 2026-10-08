# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Regression tests for reboot-safe, private Kakao skill URL refresh."""
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
import io
from urllib.parse import urlsplit

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


def test_funnel_requires_public_dns_even_when_private_magicdns_is_reachable(monkeypatch):
    monkeypatch.setattr(tunnel, 'public_addresses', lambda host: [])
    monkeypatch.setattr(tunnel.socket, 'create_connection', lambda *a, **k: pytest.fail('No public DNS; do not connect'))
    assert not tunnel.endpoint_ready('https://spark.tail-example.ts.net:10000/kakao/private-path')


def test_public_dns_rejects_private_addresses_and_never_receives_secret(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    def resolve(request, timeout):
        assert 'private-path' not in request.full_url
        assert 'type=A' in request.full_url
        return Response(json.dumps({'Answer': [
            {'type': 1, 'data': '100.94.7.102'}, {'type': 1, 'data': '127.0.0.1'},
            {'type': 1, 'data': '8.8.8.8'}, {'type': 5, 'data': 'relay.example'},
        ]}).encode())
    monkeypatch.setattr(tunnel, 'urlopen', resolve)
    assert tunnel.public_addresses('spark.tail-example.ts.net') == ['8.8.8.8']


def test_funnel_public_probe_uses_public_ip_with_hostname_tls_and_empty_body(monkeypatch):
    calls = []
    class Connection:
        def __init__(self, host, port, timeout): calls.append(('host', host, port))
        def request(self, method, path, body, headers): calls.append(('request', method, path, body))
        def getresponse(self):
            return SimpleNamespace(status=400, read=lambda limit: json.dumps(
                {'version': '2.0', 'template': {'outputs': [{}]}}).encode())
        def close(self): calls.append(('closed',))
    monkeypatch.setattr(tunnel, 'public_addresses', lambda host: ['8.8.8.8'])
    monkeypatch.setattr(tunnel.http.client, 'HTTPSConnection', Connection)
    monkeypatch.setattr(tunnel.socket, 'create_connection', lambda address, timeout: calls.append(('address', address)))
    monkeypatch.setattr(tunnel.ssl, 'create_default_context', lambda: SimpleNamespace(
        wrap_socket=lambda raw, server_hostname: calls.append(('tls', server_hostname))))
    assert tunnel.endpoint_ready('https://spark.tail-example.ts.net:10000/kakao/private-path')
    assert ('address', ('8.8.8.8', 10000)) in calls
    assert ('tls', 'spark.tail-example.ts.net') in calls
    assert ('request', 'POST', '/kakao/private-path', b'{}') in calls
    assert calls[-1] == ('closed',)


def test_funnel_public_probe_handles_dns_failure_without_secret(monkeypatch):
    def failure(host): raise URLError('DNS unavailable')
    monkeypatch.setattr(tunnel, 'public_addresses', failure)
    assert not tunnel.endpoint_ready('https://spark.tail-example.ts.net:10000/kakao/private-path')


def test_public_dns_rechecks_bypass_cached_http_nxdomain(monkeypatch):
    requests = []
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    def resolve(request, timeout):
        requests.append(request)
        return Response(b'{"Answer": []}')
    monkeypatch.setattr(tunnel, 'urlopen', resolve)
    tunnel.public_addresses('spark.tail-example.ts.net')
    tunnel.public_addresses('spark.tail-example.ts.net')
    assert requests[0].full_url != requests[1].full_url
    assert all(r.get_header('Cache-control') == 'no-cache' for r in requests)
