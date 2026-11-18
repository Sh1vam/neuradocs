import asyncio
import contextvars
import zipfile

from fastapi.testclient import TestClient

import build_api
import main
import store
from test_neuradocs import FILES, groq, point_builder_at, reply

client = TestClient(main.app)


def test_what_counts_as_a_change_request():
    for yes in ('fix the bug: the game never ends', 'solve it', 'add a reset button', 'the board is wrong'):
        assert build_api.looks_like_change(yes), yes
    for no in ('create a calculator app', 'build a new weather app', 'make another game'):
        assert not build_api.looks_like_change(no), no


def test_a_change_request_loads_the_earlier_project_and_keeps_its_files(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    first = build_api.build('Make a tic tac toe game', llm=lambda s, u: FILES, run_tests=lambda rel: (0, '1 passed'), team=False)
    seen = []
    fixed = '=== FILE: a.py ===\nx = 2\n=== END FILE ==='
    res = build_api.build('fix the bug: the game never ends', llm=lambda system, user: seen.append((system, user)) or fixed,
                          run_tests=lambda rel: (0, '1 passed'), team=False, base=tmp_path / 'builds' / first['folder'])
    system, user = seen[0]
    assert 'Change request:' in user and 'Current files:' in user and 'x = 1' in user      # it saw the old code
    assert 'bugfix-workflow' in system                                                       # and the skill for fixing bugs
    assert res['response'].startswith('**Updated `') and res['slug'] == first['slug'] and res['folder'] != first['folder']
    z = zipfile.ZipFile(tmp_path / 'out' / res['zip'])
    names = z.namelist()
    assert any(n.endswith('/tests/test_a.py') for n in names)                                # untouched files came along
    assert z.read([n for n in names if n.endswith('/a.py')][0]).decode().strip() == 'x = 2'  # the changed file is the new one


def test_the_build_endpoint_updates_the_chats_project_and_new_starts_another(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    seen = []

    def create(**kw):
        seen.append(kw['messages'][-1]['content'])
        return reply(FILES)
    monkeypatch.setattr(build_api, '_groq', groq(create))
    monkeypatch.setattr(build_api, 'sandbox_pytest', lambda rel: (0, '1 passed'))
    monkeypatch.setattr(build_api, 'TEAM', False)
    a = client.post('/api/build', json={'message': 'Make a tic tac toe game'}).json()
    assert a['response'].startswith('**Built')
    cid = a['conv_id']
    assert client.get(f'/api/chats/{cid}/build').json()['slug']
    b = client.post('/api/build', json={'message': 'fix the bug: nobody ever wins', 'conversation_id': cid}).json()
    assert b['response'].startswith('**Updated') and 'Change request:' in seen[-1] and 'Current files:' in seen[-1]
    c = client.post('/api/build', json={'message': 'new: make a calculator', 'conversation_id': cid}).json()
    assert c['response'].startswith('**Built')


def test_the_agent_can_build_and_then_revise_in_the_same_chat(monkeypatch, tmp_path):
    point_builder_at(tmp_path, monkeypatch)
    monkeypatch.setattr(build_api, '_groq', groq(lambda **kw: reply(FILES)))
    monkeypatch.setattr(build_api, 'sandbox_pytest', lambda rel: (0, '1 passed'))
    monkeypatch.setattr(build_api, 'TEAM', False)
    cid = store.create_chat()

    def run():
        build_api.CURRENT_CHAT.set(cid)
        return asyncio.run(main.tool_build_project('Make a tic tac toe game')), asyncio.run(main.tool_revise_project('the winner is never detected'))
    built, fixed = contextvars.copy_context().run(run)
    assert built.startswith('**Built') and fixed.startswith('**Updated')
    assert 'no project built earlier' in contextvars.copy_context().run(lambda: asyncio.run(main.tool_revise_project('fix it')))
