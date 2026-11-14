"""Offline tests: the model is stubbed, so no key, network or Docker is needed."""
import io
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request
import types
import zipfile
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

import build_api
import docs_api
import llm_client
import main
import store

client = TestClient(main.app)


def groq(create):
    return llm_client.GroqAdapter(NS(chat=NS(completions=NS(create=create))))


def reply(text):
    return NS(choices=[NS(message=NS(content=text, tool_calls=None))], usage=NS(prompt_tokens=1, completion_tokens=1))


class RateLimitError(Exception):
    pass


FILES = ('=== FILE: a.py ===\nx = 1\n=== END FILE ===\n'
         '=== FILE: tests/test_a.py ===\ndef test_a():\n    assert True\n=== END FILE ===\n'
         '=== FILE: ../evil.py ===\nprint("escape")\n=== END FILE ===')


def test_store_pins_search_and_cascade():
    p = store.create_project('Thesis', 'Answer formally.')
    a, b = store.create_chat(p), store.create_chat()
    store.add_message(a, 'user', 'Explain retrieval')
    store.add_message(b, 'user', 'hello')
    store.set_pinned(b, True)
    assert [c['id'] for c in store.list_chats()][:2] == [b, a]            # pinned first
    assert [c['id'] for c in store.list_chats(q='retrieval')] == [a]       # search reads message text
    assert 'Answer formally.' in store.system_prompt_for(a, 'Base')
    store.delete_project(p)
    assert not store.chat_exists(a) and store.chat_exists(b)               # cascade


def test_adapter_adds_reasoning_effort_only_for_gpt_oss():
    seen = []
    ad = groq(lambda **kw: seen.append(kw) or reply('ok'))
    ad.chat.completions.create(model='openai/gpt-oss-120b', messages=[])
    ad.chat.completions.create(model='other', messages=[])
    ad.chat.completions.create(model='openai/gpt-oss-120b', messages=[], extra_body={'reasoning_effort': 'high'})
    assert seen[0]['extra_body'] == {'reasoning_effort': 'low'}
    assert 'extra_body' not in seen[1]
    assert seen[2]['extra_body'] == {'reasoning_effort': 'high'}


def test_chat_keeps_history_and_project_instructions(monkeypatch):
    calls = []
    monkeypatch.setattr(main, 'groq_client', groq(lambda **kw: calls.append(kw) or reply('Hi back')))
    pid = client.post('/api/projects', json={'name': 'P', 'instructions': 'Be brief.'}).json()['id']
    first = client.post('/api/chat', json={'message': 'One', 'project_id': pid, 'stream': False}).json()
    client.post('/api/chat', json={'message': 'Two', 'conversation_id': first['conv_id'], 'stream': False})
    assert 'Be brief.' in calls[-1]['messages'][0]['content']
    assert [m['role'] for m in calls[-1]['messages']] == ['system', 'user', 'assistant', 'user']
    assert len(client.get(f"/api/chats/{first['conv_id']}/messages").json()) == 4


def test_partial_reply_is_saved_when_the_stream_breaks(monkeypatch):
    def create(**kw):
        def gen():
            yield NS(choices=[NS(delta=NS(content='Hel'))])
            raise RuntimeError('connection lost')
        return gen()
    monkeypatch.setattr(main, 'groq_client', groq(create))
    r = client.post('/api/chat', json={'message': 'hi', 'stream': True})
    cid = [l for l in r.text.split('\n') if l.startswith('data: ') and 'conv_id' in l][0].split('"conv_id": "')[1].split('"')[0]
    assert client.get(f'/api/chats/{cid}/messages').json()[-1]['content'] == 'Hel'


def test_rate_limit_message_is_readable(monkeypatch):
    def create(**kw):
        raise RateLimitError('Error code: 429 - rate limit reached')
    monkeypatch.setattr(main, 'groq_client', groq(create))
    assert 'wait a minute' in client.post('/api/chat', json={'message': 'hi', 'stream': True}).text
    assert 'wait a minute' in client.post('/api/mcp/chat', json={'message': 'hi'}).json()['detail']


def point_builder_at(tmp_path, monkeypatch):
    monkeypatch.setattr(build_api, 'BUILDS', tmp_path / 'builds')
    monkeypatch.setattr(build_api, '_out', tmp_path / 'out')


def test_build_fix_loop_zip_and_path_guard(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    seen, runs = [], iter([(1, 'FAILED test_a: assert -1 == 3'), (0, '1 passed')])
    llm = lambda system, user: seen.append(user) or FILES                    # noqa: E731
    res = build_api.build('Make a thing', llm=llm, run_tests=lambda rel: next(runs))
    names = zipfile.ZipFile(tmp_path / 'out' / res['zip']).namelist()
    assert (res['status'], res['rounds']) == ('passed', 2)
    assert 'assert -1 == 3' in seen[1] and 'x = 1' in seen[1]                # the fix round sees the failure and the files
    assert not any('evil' in n for n in names) and not (tmp_path / 'evil.py').exists()


def test_build_keeps_round_one_when_a_later_round_fails(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    calls = []
    def llm(system, user):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('limit')
        return FILES
    res = build_api.build('Make a thing', llm=llm, run_tests=lambda rel: (1, 'FAILED'))
    assert res['status'] == 'failed' and 'Stopped in round 2' in res['response']
    assert (tmp_path / 'out' / res['zip']).exists()


def test_build_waits_out_a_rate_limit(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    n, last = {'c': 0}, {}
    RL = type('RateLimitError', (Exception,), {})
    def create(**kw):
        n['c'] += 1
        last.update(kw)
        if n['c'] == 1:
            e = RL('429')
            e.response = NS(headers={'retry-after': '0.01'})
            raise e
        return reply(FILES)
    monkeypatch.setattr(build_api, '_groq', groq(create))
    res = build_api.build('Make a thing', run_tests=lambda rel: (0, 'ok'))
    assert res['status'] == 'passed' and n['c'] == 2
    assert last['extra_body'] == {'reasoning_effort': 'medium'}


def test_upload_indexes_only_the_new_file(monkeypatch, tmp_path):
    monkeypatch.setattr(docs_api, 'DT', tmp_path / 'docuteam')
    got = {}
    fake = types.ModuleType('knowledge')
    fake.ingest = lambda folder: got.update(files=sorted(p.name for p in pathlib.Path(folder).glob('*'))) or 7
    monkeypatch.setitem(sys.modules, 'knowledge', fake)
    r = client.post('/api/docs/upload', files={'file': ('Team Policy (v2).txt', b'Remote work is allowed 3 days.', 'text/plain')})
    assert r.json() == {'ok': True, 'file': 'Team_Policy_v2_.txt', 'chunks': 7}
    assert got['files'] == ['Team_Policy_v2_.txt']
    assert (tmp_path / 'docuteam' / 'workspace' / 'docs' / 'Team_Policy_v2_.txt').exists()
    assert client.post('/api/docs/upload', files={'file': ('e.txt', b'   ', 'text/plain')}).status_code == 422


def tool_call_reply():
    call = NS(id='1', function=NS(name='ask_documents', arguments='{"question": "x"}'))
    return NS(choices=[NS(message=NS(content='', tool_calls=[call]))], usage=NS(prompt_tokens=1, completion_tokens=1))


async def fake_ask(question):
    return 'the handbook says 3 days'


def test_agent_stream_reports_tool_progress_and_saves(monkeypatch):
    rounds = iter([tool_call_reply(), reply('Final answer')])
    monkeypatch.setattr(main, 'groq_client', groq(lambda **kw: next(rounds)))
    monkeypatch.setitem(main.MCP_TOOLS['ask_documents'], 'handler', fake_ask)
    r = client.post('/api/mcp/chat', json={'message': 'How many remote days?', 'stream': True})
    events = [__import__('json').loads(l[6:]) for l in r.text.split('\n') if l.startswith('data: ')]
    assert 'conv_id' in events[0]
    assert [e['status'] for e in events if 'tool' in e] == ['tool_start', 'tool_done']
    assert events[-1]['done'] and events[-1]['response'] == 'Final answer'
    saved = client.get(f"/api/chats/{events[0]['conv_id']}/messages").json()
    assert [m['role'] for m in saved] == ['user', 'assistant']


def test_agent_gives_an_answer_even_when_every_round_uses_a_tool(monkeypatch):
    monkeypatch.setattr(main, 'groq_client', groq(lambda **kw: tool_call_reply() if 'tools' in kw else reply('Wrapped up')))
    monkeypatch.setitem(main.MCP_TOOLS['ask_documents'], 'handler', fake_ask)
    d = client.post('/api/mcp/chat', json={'message': 'loop forever'}).json()
    assert d['response'] == 'Wrapped up' and len(d['tool_calls']) == 5


def test_build_stays_in_the_workspace_and_reports_usage(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    monkeypatch.setattr(build_api, '_groq', groq(lambda **kw: reply(FILES)))
    monkeypatch.setattr(build_api, 'sandbox_pytest', lambda rel: (0, '2 passed'))
    before = client.get('/api/tokens/stats').json()
    d = client.post('/api/build', json={'message': 'Create a django project with a health view'}).json()
    assert 'Project folder:' in d['response'] and '2 passed' in d['response']
    assert len(list((tmp_path / 'builds').glob('*/a.py'))) == 1            # the project was kept, not deleted
    assert d['usage']['prompt'] == 1 and d['usage']['completion'] == 1 and 'cost' in d['usage']
    after = client.get('/api/tokens/stats').json()
    assert after != before                                                  # the sidebar totals moved


def test_agent_reply_reports_token_usage(monkeypatch):
    answer = NS(choices=[NS(message=NS(content='ok', tool_calls=None))], usage=NS(prompt_tokens=10, completion_tokens=5))
    monkeypatch.setattr(main, 'groq_client', groq(lambda **kw: answer))
    d = client.post('/api/mcp/chat', json={'message': 'hello'}).json()
    assert d['usage']['prompt'] == 10 and d['usage']['completion'] == 5 and d['usage']['cost'] > 0


def test_old_chats_move_to_the_new_location(monkeypatch, tmp_path):
    legacy, new = tmp_path / 'old' / 'neurachat.db', tmp_path / 'home' / 'neurachat.db'
    legacy.parent.mkdir()
    monkeypatch.setattr(store, 'DB', legacy)
    store.init()
    cid = store.create_chat(None, 'Old chat')                           # creates the old database file
    monkeypatch.setattr(store, 'LEGACY', legacy)
    monkeypatch.setattr(store, 'DEFAULT_DB', new)
    monkeypatch.setattr(store, 'DB', new)
    store.init()
    assert store.chat_exists(cid) and store.counts()[1] >= 1


def test_agent_and_build_together_force_the_builder_and_keep_the_link(monkeypatch):
    calls = []
    call = NS(id='1', function=NS(name='build_project', arguments='{"spec": "A django app"}'))
    first = NS(choices=[NS(message=NS(content='', tool_calls=[call]))], usage=NS(prompt_tokens=1, completion_tokens=1))
    rounds = iter([first, reply('All done, enjoy!')])                       # the model forgets to repeat the link
    monkeypatch.setattr(main, 'groq_client', groq(lambda **kw: calls.append(kw) or next(rounds)))

    async def fake_build(spec):
        return 'Built `x`. Project folder: `docuteam/workspace/code/builds/x-1`\n[Download x.zip](/api/download/x-1.zip)'
    monkeypatch.setitem(main.MCP_TOOLS['build_project'], 'handler', fake_build)
    d = client.post('/api/mcp/chat', json={'message': 'Create a django project', 'build': True}).json()
    assert 'Build mode is ON' in calls[0]['messages'][0]['content']
    assert 'All done' in d['response'] and '/api/download/x-1.zip' in d['response']
    assert [t['tool'] for t in d['tool_calls']] == ['build_project']
    calls.clear()
    monkeypatch.setattr(main, 'groq_client', groq(lambda **kw: calls.append(kw) or reply('hello')))
    client.post('/api/mcp/chat', json={'message': 'hi'})
    assert 'Build mode is ON' not in calls[0]['messages'][0]['content']      # only when Build is on


PLAN = ('{"options": [{"name": "Django + SQLite", "approach": "a", "score": 5, "why": "batteries included"},'
        '{"name": "Flask", "approach": "b", "score": 3, "why": "light"}, {"name": "FastAPI", "approach": "c", "score": 4, "why": "async"}],'
        '"chosen": 0, "spec": "Build a Django todo app with pytest-django tests."}')


def test_team_researches_plans_codes_and_tests(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    seen, runs, replies = [], iter([(1, 'FAILED x\n1 failed in 0.1s'), (0, '3 passed in 0.2s')]), iter([PLAN, FILES, FILES])
    llm = lambda system, user: seen.append(user) or next(replies)                      # noqa: E731
    search = lambda q: [{'name': 'octo/todo', 'description': 'A todo app', 'stars': 120, 'url': 'https://github.com/octo/todo'}]
    res = build_api.build('Create a todo app', llm=llm, run_tests=lambda rel: next(runs), team=True, search=search)
    text = res['response']
    assert 'octo/todo' in seen[0] and 'Build a Django todo app' in seen[1]       # the planner saw the projects, the coder the plan
    assert 'Team log' in text and 'Researcher' in text and 'chose "Django + SQLite"' in text and 'Options compared' in text
    assert '1 failed' in text and '3 passed' in text and res['status'] == 'passed'


def test_team_continues_without_search_or_a_plan(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    def down(q):
        raise OSError('no internet')
    replies = iter(['not json at all', FILES])
    res = build_api.build('Create a todo app', llm=lambda s, u: next(replies), run_tests=lambda rel: (0, '1 passed'), team=True, search=down)
    assert 'search unavailable' in res['response'] and 'no usable plan' in res['response'] and res['status'] == 'passed'


def start_runner(tmp_path, monkeypatch):
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    root = pathlib.Path(__file__).resolve().parent.parent
    env = {**os.environ, 'PORT': str(port), 'HOST': '127.0.0.1', 'SANDBOX_TOKEN': 'secret', 'WORKDIR': str(tmp_path / 'work')}
    proc = subprocess.Popen([sys.executable, str(root / 'runner' / 'server.py')], env=env)
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    monkeypatch.setenv('SANDBOX_URL', f'http://127.0.0.1:{port}')
    monkeypatch.setenv('SANDBOX_TOKEN', 'secret')
    return proc


def test_remote_sandbox_runs_tests_and_refuses_bad_jobs(monkeypatch, tmp_path):
    import sandbox_client
    proc = start_runner(tmp_path, monkeypatch)
    try:
        rc, out = sandbox_client.run({'test_ok.py': 'def test_ok():\n    assert 1 + 1 == 2\n'}, ['python', '-m', 'pytest', '-q'], 60)
        assert rc == 0 and '1 passed' in out
        assert sandbox_client.run({'../evil.py': 'x'}, ['python', '-c', '1'], 10)[0] == 2           # path traversal refused
        assert 'not allowed' in sandbox_client.run({}, ['bash', '-c', 'echo hi'], 10)[1]            # only python and pytest
        assert sandbox_client.run({'slow.py': 'import time\ntime.sleep(5)\n'}, ['python', 'slow.py'], 1)[0] == 124   # timeout
        monkeypatch.setenv('SANDBOX_TOKEN', 'wrong')
        with pytest.raises(RuntimeError):
            sandbox_client.run({}, ['python', '-c', '1'], 5)
        monkeypatch.setenv('SANDBOX_TOKEN', 'secret')
        proj = tmp_path / 'builds' / 'p-1'
        (proj / 'tests').mkdir(parents=True)
        (proj / 'conftest.py').write_text('')
        (proj / 'a.py').write_text('x = 2\n')
        (proj / 'tests' / 'test_a.py').write_text('from a import x\n\ndef test_a():\n    assert x == 2\n')
        monkeypatch.setattr(build_api, 'BUILDS', tmp_path / 'builds')
        assert build_api.sandbox_pytest('builds/p-1')[0] == 0                # the builder uses the service when SANDBOX_URL is set
        assert 'exit 0' in docs_api.run_python_sandboxed('print(41 + 1)') and '42' in docs_api.run_python_sandboxed('print(41 + 1)')
    finally:
        proc.terminate()


def test_basic_auth_guards_everything_but_health():
    from fastapi import FastAPI
    import auth
    guarded = FastAPI()

    @guarded.get('/api/health')
    def health():
        return {'ok': True}

    @guarded.get('/secret')
    def secret():
        return {'secret': 1}
    guarded.add_middleware(auth.BasicAuth, password='pw')
    c = TestClient(guarded)
    assert c.get('/api/health').status_code == 200
    r = c.get('/secret')
    assert r.status_code == 401 and 'Basic' in r.headers['www-authenticate']
    assert c.get('/secret', auth=('anyone', 'wrong')).status_code == 401
    assert c.get('/secret', auth=('anyone', 'pw')).status_code == 200


def test_checkpoints_use_a_hidden_repo_and_leave_the_code_folder_plain(monkeypatch, tmp_path):
    if not shutil.which('git'):
        pytest.skip('git is not installed')
    docs_api._path()
    import safe_shell
    code = tmp_path / 'ws' / 'code'
    code.mkdir(parents=True)
    monkeypatch.setattr(safe_shell, 'WORKSPACE', code)
    monkeypatch.setattr(safe_shell, 'GITDIR', tmp_path / 'ws' / '.checkpoints.git')
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)           # an OUTER repository that must stay untouched
    (code / 'a.py').write_text('x = 1\n')
    assert safe_shell.run_command(['git', 'add', '-A'])[0] == 0
    rc, out = safe_shell.run_command(['git', 'commit', '-m', 'checkpoint'])
    assert rc == 0, out
    assert not list(code.glob('.git*'))                                       # the code folder stays a plain folder
    assert (tmp_path / 'ws' / '.checkpoints.git').exists()
    outer = subprocess.run(['git', 'log', '--oneline'], cwd=tmp_path, capture_output=True, text=True)
    assert 'checkpoint' not in outer.stdout                                   # the outer repository got no commit


def test_egress_allowlist_and_private_address_guard():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'egress'))
    import proxy
    public = lambda h, p: ['151.101.0.223']                                                        # noqa: E731
    assert proxy.check_target('pypi.org', 443, ['pypi.org'], resolver=public) == (None, '151.101.0.223')
    assert proxy.check_target('files.pypi.org', 443, ['pypi.org'], resolver=public)[0] is None   # a subdomain of an allowed domain
    assert 'allowlist' in proxy.check_target('evil.com', 443, ['pypi.org'], resolver=public)[0]
    assert 'allowlist' in proxy.check_target('notpypi.org', 443, ['pypi.org'], resolver=public)[0]   # the suffix trick
    assert 'port' in proxy.check_target('pypi.org', 22, ['pypi.org'], resolver=public)[0]
    for inside in ('127.0.0.1', '10.0.0.5', '192.168.1.9', '169.254.169.254', '172.17.0.2', '::1'):
        why = proxy.check_target('pypi.org', 443, ['pypi.org'], resolver=lambda h, p, ip=inside: [ip])[0]
        assert why and 'non-public' in why                                                         # DNS pointing inside is refused


def test_egress_proxy_tunnels_only_what_is_allowed():
    import asyncio
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'egress'))
    import proxy

    async def scenario():
        async def echo(r, w):
            w.write(await r.read(100))
            await w.drain()
            w.close()
        echo_srv = await asyncio.start_server(echo, '127.0.0.1', 0)
        eport = echo_srv.sockets[0].getsockname()[1]
        mk = lambda allow, private: asyncio.start_server(                                          # noqa: E731
            lambda r, w: proxy.handle(r, w, allow, private, {eport}), '127.0.0.1', 0)
        open_srv, closed_srv = await mk(['127.0.0.1'], True), await mk(['127.0.0.1'], False)

        async def connect(srv, host):
            r, w = await asyncio.open_connection('127.0.0.1', srv.sockets[0].getsockname()[1])
            w.write(f'CONNECT {host}:{eport} HTTP/1.1\r\n\r\n'.encode())
            status = (await r.readuntil(b'\r\n\r\n')).split(b' ')[1]
            if status == b'200':
                w.write(b'ping')
                return status, await r.read(10)
            return status, b''
        return (await connect(open_srv, '127.0.0.1'), await connect(open_srv, 'example.org'), await connect(closed_srv, '127.0.0.1'))
    ok, not_listed, private = asyncio.run(scenario())
    assert ok == (b'200', b'ping')                      # allowed and public-or-allowed-private: the bytes come back
    assert not_listed[0] == b'403'                      # not on the allowlist
    assert private[0] == b'403'                         # loopback is refused unless the test switch is on


def test_sandbox_install_flag_and_dependency_folder(monkeypatch, tmp_path):
    import sandbox_client
    proc = start_runner(tmp_path, monkeypatch)
    try:
        assert sandbox_client.run({'t.py': 'print(7)'}, ['python', 't.py'], 20, install=True)[0] == 0          # no requirements.txt: nothing to do
        rc, out = sandbox_client.run({'requirements.txt': 'no-such-package-xyz-123==9.9\n'}, ['python', '-c', '1'], 60, install=True)
        assert rc == 3 and 'pip install failed' in out                                                     # a failed install stops the job
        assert build_api._skip(pathlib.Path('p/.deps/x.py'))                                               # dependencies are never zipped
    finally:
        proc.terminate()


def test_builder_follows_matching_skills(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    seen = []
    llm = lambda system, user: seen.append(system) or FILES                    # noqa: E731
    res = build_api.build('Create a django todo app with login', llm=llm, run_tests=lambda rel: (0, '1 passed'), team=False)
    assert 'Skill "django-project"' in seen[0] and 'pytest.ini' in seen[0]       # the Coder got the saved workflow
    assert 'Skills' in res['response'] and 'following django-project' in res['response']
    seen.clear()
    monkeypatch.setenv('SKILLS', '0')
    build_api.build('Create a django todo app with login', llm=llm, run_tests=lambda rel: (0, '1 passed'), team=False)
    assert 'Skill "' not in seen[0]                                               # SKILLS=0 switches it off
