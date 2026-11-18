import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

import connectors
import llm_client
import main

client = TestClient(main.app)


class Echo(BaseHTTPRequestHandler):
    def handle_any(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n).decode() if n else ''
        payload = json.dumps({'method': self.command, 'path': self.path, 'auth': self.headers.get('Authorization'),
                              'key': self.headers.get('X-API-Key'), 'body': body}).encode()
        redirect = self.path.startswith('/redir')
        self.send_response(302 if redirect else 200)
        if redirect:
            self.send_header('Location', '/secret')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_any

    def log_message(self, *args):
        pass


@pytest.fixture
def api(monkeypatch, tmp_path):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), Echo)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv('CONNECTORS_FILE', str(tmp_path / 'c.json'))
    yield f'http://127.0.0.1:{srv.server_address[1]}'
    srv.shutdown()


def register(base, **kw):
    connectors._save([{'name': 'demo', 'description': 'A test API', 'base_url': base, 'token_env': '', 'token_header': 'Authorization',
                       'token_prefix': 'Bearer ', 'allow_write': False, **kw}])


def test_a_connector_sends_the_token_from_env_and_never_stores_it(api, monkeypatch):
    monkeypatch.setenv('DEMO_TOKEN', 's3cret')
    register(api, token_env='DEMO_TOKEN')
    r = connectors.call('demo', 'GET', '/items', {'q': 'a b'}, allow_private=True)
    assert r.startswith('HTTP 200') and '"auth": "Bearer s3cret"' in r and '/items?q=a+b' in r
    assert 's3cret' not in connectors._file().read_text() and 's3cret' not in connectors.catalog_prompt()      # never on disk or in a prompt


def test_other_header_styles_work(api, monkeypatch):
    monkeypatch.setenv('DEMO_TOKEN', 'k1')
    register(api, token_env='DEMO_TOKEN', token_header='X-API-Key', token_prefix='')
    r = connectors.call('demo', 'GET', '/', allow_private=True)
    assert '"key": "k1"' in r and '"auth": null' in r


def test_connectors_are_read_only_unless_you_allow_changes(api):
    register(api)
    with pytest.raises(ValueError, match='read-only'):
        connectors.call('demo', 'POST', '/x', body={'a': 1}, allow_private=True)
    register(api, allow_write=True)
    r = connectors.call('demo', 'POST', '/x', body={'a': 1}, allow_private=True)
    assert '"method": "POST"' in r and '\\"a\\": 1' in r


def test_paths_cannot_leave_the_connector(api):
    register(api)
    for bad in ('items', '/../etc/passwd', 'http://evil.example/x', '/a@evil.example', '/x\r\nHost: evil'):
        with pytest.raises(ValueError):
            connectors.call('demo', 'GET', bad, allow_private=True)


def test_redirects_are_not_followed(api):
    register(api)
    assert connectors.call('demo', 'GET', '/redir', allow_private=True).startswith('HTTP 302')


def test_private_addresses_are_refused_by_default(api):
    register(api)
    with pytest.raises(ValueError, match='public'):
        connectors.call('demo', 'GET', '/')


def test_a_missing_token_variable_says_which(api, monkeypatch):
    monkeypatch.delenv('NOPE_TOKEN', raising=False)
    register(api, token_env='NOPE_TOKEN')
    with pytest.raises(ValueError, match='NOPE_TOKEN'):
        connectors.call('demo', 'GET', '/', allow_private=True)


def test_adding_checks_what_you_type(tmp_path, monkeypatch):
    monkeypatch.setenv('CONNECTORS_FILE', str(tmp_path / 'c.json'))
    assert connectors.add('github', 'GitHub API', 'https://api.github.com', 'GITHUB_TOKEN') == 'github'
    for kwargs in ({'name': 'Bad Name', 'base_url': 'https://x.com'}, {'name': 'a', 'base_url': 'http://x.com'},
                   {'name': 'a', 'base_url': 'https://user:pw@x.com'}, {'name': 'a', 'base_url': 'https://x.com', 'token_env': 'ghp_abc123secret'},
                   {'name': 'a', 'base_url': 'https://x.com', 'token_header': 'Bad Header'}):
        with pytest.raises(ValueError):
            connectors.add(description='d', **kwargs)                    # a pasted token is refused: only the variable NAME is accepted
    assert 'github' in connectors.catalog_prompt() and 'read-only' in connectors.catalog_prompt()


def test_api_page_and_agent_tool(tmp_path, monkeypatch):
    monkeypatch.setenv('CONNECTORS_FILE', str(tmp_path / 'c.json'))
    monkeypatch.setenv('GITHUB_TOKEN', 'x')
    assert client.post('/api/connectors', json={'name': 'github', 'description': 'GitHub API', 'base_url': 'https://api.github.com', 'token_env': 'GITHUB_TOKEN'}).status_code == 200
    listed = client.get('/api/connectors').json()['connectors']
    assert listed[0]['name'] == 'github' and listed[0]['token_set'] is True
    assert client.post('/api/connectors', json={'name': 'x', 'description': 'd', 'base_url': 'http://plain.example'}).status_code == 400
    assert client.post('/api/connectors/nope/test', json={'path': '/'}).status_code == 400
    assert 'Connector error' in asyncio.run(main.tool_call_connector('nope', 'GET', '/'))
    assert client.delete('/api/connectors/github').status_code == 200 and client.delete('/api/connectors/github').status_code == 404
    assert 'Add a connector' in client.get('/connectors').text


def test_the_agent_prompt_lists_connectors(tmp_path, monkeypatch):
    monkeypatch.setenv('CONNECTORS_FILE', str(tmp_path / 'c.json'))
    connectors.add('github', 'GitHub API', 'https://api.github.com')
    seen = []

    def create(**kw):
        seen.append(kw)
        return NS(choices=[NS(message=NS(content='ok', tool_calls=None))], usage=NS(prompt_tokens=1, completion_tokens=1))
    monkeypatch.setattr(main, 'groq_client', llm_client.GroqAdapter(NS(chat=NS(completions=NS(create=create)))))
    client.post('/api/mcp/chat', json={'message': 'hi'})
    assert 'github: GitHub API (api.github.com, read-only)' in seen[0]['messages'][0]['content']
