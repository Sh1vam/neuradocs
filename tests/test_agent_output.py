import json
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

import build_api
import llm_client
import main
from test_neuradocs import FILES, point_builder_at

client = TestClient(main.app)


def reply(text, finish='stop'):
    return NS(choices=[NS(message=NS(content=text, tool_calls=None), finish_reason=finish)], usage=NS(prompt_tokens=5, completion_tokens=20))


def groq(create):
    return llm_client.GroqAdapter(NS(chat=NS(completions=NS(create=create))))


def set_up(monkeypatch, tmp_path, agent):
    point_builder_at(tmp_path, monkeypatch)
    monkeypatch.setattr(main, 'groq_client', groq(agent))
    monkeypatch.setattr(build_api, '_groq', groq(lambda **kw: reply(FILES)))          # the builder's own model calls
    monkeypatch.setattr(build_api, 'sandbox_pytest', lambda rel: (0, '1 passed'))
    monkeypatch.setattr(build_api, 'TEAM', False)


def test_an_empty_model_answer_becomes_a_clear_message_and_the_agent_has_room_to_think(monkeypatch):
    seen = []
    monkeypatch.setattr(main, 'groq_client', groq(lambda **kw: seen.append(kw) or reply('', 'length')))
    d = client.post('/api/mcp/chat', json={'message': 'hello'}).json()
    assert d['response'] == main.NO_ANSWER and 'Thinking' in d['response']
    assert seen[0]['max_tokens'] == 4096                                              # was 2048: reasoning ate all of it


def test_the_last_attempt_thinks_less(monkeypatch):
    calls = []

    def create(**kw):
        calls.append(kw)
        return reply('', 'length') if len(calls) == 1 else reply('Here is the answer')
    monkeypatch.setattr(main, 'groq_client', groq(create))
    assert client.post('/api/mcp/chat', json={'message': 'hello'}).json()['response'] == 'Here is the answer'
    assert calls[1]['extra_body'] == {'reasoning_effort': 'low'}


def test_build_mode_builds_even_when_the_model_does_not(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, lambda **kw: reply('', 'length'))
    d = client.post('/api/mcp/chat', json={'message': 'Create a Django codebase for tic tac toe', 'build': True}).json()
    assert 'Built `' in d['response'] and '/api/download/' in d['response']
    assert [t['tool'] for t in d['tool_calls']] == ['build_project']


def test_a_clear_project_request_is_built_when_the_model_gives_nothing(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, lambda **kw: reply('', 'length'))                    # no Build button pressed
    d = client.post('/api/mcp/chat', json={'message': 'Create a Django codebase for playing the Tic-Tac-Toe game'}).json()
    assert 'Built `' in d['response'] and d['tool_calls'][0]['tool'] == 'build_project'


def test_a_project_request_answered_in_text_is_left_alone(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, lambda **kw: reply('Happy to help. Which database do you want?'))
    d = client.post('/api/mcp/chat', json={'message': 'Create a Django codebase for playing the Tic-Tac-Toe game'}).json()
    assert d['response'] == 'Happy to help. Which database do you want?' and d['tool_calls'] == []


def test_the_stream_reports_the_forced_build(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, lambda **kw: reply('', 'length'))
    r = client.post('/api/mcp/chat', json={'message': 'Create a Django codebase for tic tac toe', 'build': True, 'stream': True})
    events = [json.loads(line[6:]) for line in r.text.split('\n') if line.startswith('data: ')]
    assert ('build_project', 'tool_start') in [(e.get('tool'), e.get('status')) for e in events]
    assert events[-1]['done'] and '/api/download/' in events[-1]['response']


def test_plain_chat_says_so_when_the_model_returns_nothing(monkeypatch):
    def create(**kw):
        return iter([NS(choices=[NS(delta=NS(content=None))])])
    monkeypatch.setattr(main, 'groq_client', groq(create))
    r = client.post('/api/chat', json={'message': 'hi', 'stream': True})
    assert 'returned no text' in r.text


def test_what_counts_as_a_project_request():
    for yes in ('Create a Django codebase for playing the Tic-Tac-Toe game', 'build a new weather app', 'make a game'):
        assert build_api.looks_like_project(yes), yes
    for no in ('what is BUILD_TEAM=10 in my env', 'explain how a project is structured', 'fix the bug in the game'):
        assert not build_api.looks_like_project(no), no
