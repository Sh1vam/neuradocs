"""Offline tests: no API key, no models, no Docker, no network needed.
Run from the project folder:  pytest -q tests"""
import json
import os

import pytest

import agent_core
import safe_shell
import safe_web
import safety
import tools_basic
import usage
from agent_core import Agent, Tool
from check import check_citations
from chunkers import chunk_recursive
from task_state import TaskState
from team import parse_json


# ---------- safe_web ----------
@pytest.mark.parametrize('url', [
    'http://127.0.0.1/', 'http://localhost:8000/', 'http://[::1]/',
    'http://169.254.169.254/latest/meta-data/', 'file:///C:/Windows/win.ini', 'ftp://example.com/x'])
def test_check_url_blocks_unsafe_targets(url):
    with pytest.raises(ValueError):
        safe_web.check_url(url)


def test_domain_allowlist():
    with pytest.raises(ValueError):
        safe_web.check_url('https://evil.example.org/', allow_domains=['docs.python.org'])


def test_untrusted_wrapper_and_invisible_characters():
    text = safe_web.to_untrusted_text('<html><body><p>Hello\u200b world, this is a long enough sentence to extract.</p></body></html>')
    assert '\u200b' not in text
    assert safe_web.wrap('https://x.test', 'abc').startswith('<untrusted_web_content')


# ---------- citations and json ----------
def test_check_citations_handles_groups_and_invalid_ids():
    r = check_citations('Yes [1, 2] and also [9].', {'1', '2', '3'})
    assert r['cited'] == ['1', '2', '9'] and r['invalid'] == ['9']


def test_parse_json_tolerates_fences_and_rejects_text():
    assert parse_json('```json\n{"a": 1}\n```') == {'a': 1}
    with pytest.raises(ValueError):
        parse_json('no json here')


# ---------- chunkers ----------
def test_chunk_recursive_respects_limit():
    text = ' '.join('word' + str(i) for i in range(500))
    chunks = chunk_recursive(text, 100)
    assert all(len(c.split()) <= 100 for c in chunks) and len(chunks) >= 5


# ---------- task state ----------
def test_task_state_saves_atomically_and_resumes(tmp_path):
    p = tmp_path / 's.json'
    st = TaskState(p)
    st.d['goal'] = 'g'
    st.d['plan'] = [{'title': 'one', 'status': 'todo'}, {'title': 'two', 'status': 'todo'}]
    st.apply({'step_index': 0, 'status': 'done', 'last_result': 'ok', 'next_action': 'do two'})
    st.save()
    assert not (tmp_path / 's.tmp').exists()
    again = TaskState(p)
    assert again.d['plan'][0]['status'] == 'done' and 'do two' in again.pinned()
    again.apply({'step_index': 99, 'status': 'bogus'})            # invalid updates are ignored
    assert again.d['plan'][1]['status'] == 'todo'


# ---------- tools_basic (workspace confinement) ----------
@pytest.fixture
def ws(tmp_path, monkeypatch):
    (tmp_path / 'drafts').mkdir()
    (tmp_path / 'logs').mkdir()
    monkeypatch.setattr(tools_basic, 'ROOT_DIR', tmp_path.resolve())
    return tmp_path


def test_write_only_inside_drafts(ws):
    assert 'wrote' in tools_basic.write_file('drafts/a.md', 'hi')
    for bad in ['../x.txt', 'notes.txt', 'logs/x.txt', 'docs/x.txt']:
        with pytest.raises(PermissionError):
            tools_basic.write_file(bad, 'no')


def test_read_blocks_escape_and_logs(ws):
    (ws / 'logs' / 'usage.jsonl').write_text('secret')
    with pytest.raises(PermissionError):
        tools_basic.read_file('../../etc/passwd')
    with pytest.raises(PermissionError):
        tools_basic.read_file('logs/usage.jsonl')


# ---------- safe_shell policy ----------
def test_command_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(safe_shell, 'WORKSPACE', tmp_path.resolve())
    for bad in [['rm', '-rf', '/'], ['powershell', '-c', 'x'], ['git', 'push'], ['git', 'reset', '--hard'],
                ['python', '../outside.py'], ['pytest', str(tmp_path.parent)], []]:
        with pytest.raises(PermissionError):
            safe_shell.check_command(bad)
    code, out = safe_shell.run_command(['python', '-c', 'print(41 + 1)'])
    assert code == 0 and '42' in out


# ---------- agent core (fake model) ----------
@pytest.fixture
def agent_env(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, 'LOG', tmp_path / 'usage.jsonl')
    monkeypatch.setattr(agent_core, 'TRACE', tmp_path / 'traces.jsonl')
    monkeypatch.setattr(safety, 'STOP_FILE', tmp_path / 'STOP')
    return tmp_path


def scripted(replies):
    it = iter(replies)
    return lambda provider, system, tr, tools=None, max_tokens=1500: next(it)


def test_agent_handles_unknown_tool_denied_write_and_finishes(agent_env, monkeypatch):
    wrote = []
    write = Tool('write_file', 'w', {'type': 'object', 'properties': {}}, lambda **a: wrote.append(a), risk='write')
    replies = [
        {'text': '', 'calls': [{'id': '1', 'name': 'no_such_tool', 'args': {}}], 'tokens': 10},
        {'text': '', 'calls': [{'id': '2', 'name': 'write_file', 'args': {'path': 'x'}}], 'tokens': 10},
        {'text': 'all done', 'calls': [], 'tokens': 10},
    ]
    monkeypatch.setattr(agent_core, 'chat', scripted(replies))
    agent = Agent('t', 'groq', 'sys', [write], approve=lambda *a: False)
    text, tr = agent.run('task')
    results = [m['result'] for m in tr if m['role'] == 'tool']
    assert text == 'all done' and wrote == []
    assert 'unknown tool' in results[0] and 'not approved' in results[1]
    assert usage.today_total() == 30
    assert json.loads((agent_env / 'traces.jsonl').read_text().splitlines()[0])['outcome'] == 'done'


def test_agent_step_limit_and_kill_switch(agent_env, monkeypatch):
    loop = {'text': '', 'calls': [{'id': 'x', 'name': 'echo', 'args': {}}], 'tokens': 1}
    echo = Tool('echo', 'e', {'type': 'object', 'properties': {}}, lambda: 'ok')
    monkeypatch.setattr(agent_core, 'chat', lambda *a, **k: loop)
    text, _ = Agent('t', 'groq', 's', [echo], max_steps=3).run('go')
    assert text.startswith('STOPPED: step limit')
    (agent_env / 'STOP').write_text('x')
    text, _ = Agent('t', 'groq', 's', [echo]).run('go')
    assert text == 'STOPPED: kill switch'


def test_stop_folder_does_not_trip_the_switch(tmp_path, monkeypatch):
    (tmp_path / 'STOP').mkdir()                                  # the bug in the uploaded project
    monkeypatch.setattr(safety, 'STOP_FILE', tmp_path / 'STOP')
    assert safety.should_stop() is False


def test_tool_output_is_capped(agent_env):
    big = Tool('big', 'b', {'type': 'object', 'properties': {}}, lambda: 'x' * 10000)
    out = Agent('t', 'groq', 's', [big]).execute({'name': 'big', 'args': {}})
    assert len(out) == agent_core.RESULT_CAP


# ---------- llm.ask fake mode and token guard ----------
def test_ask_fake_mode_returns_parseable_json(monkeypatch):
    monkeypatch.setenv('USE_FAKE_LLM', '1')
    import llm
    assert parse_json(llm.ask('route', 's', 'u'))['route'] == 'docs'
    assert 'FAKE' in llm.ask('answer', 's', 'u')


def test_ask_rejects_oversized_prompt(monkeypatch):
    monkeypatch.delenv('USE_FAKE_LLM', raising=False)
    import llm
    with pytest.raises(ValueError):
        llm.ask('answer', 's', 'x' * 20000)


# ---------- prompts / role cards ----------
def test_answerer_card_contains_refusal_and_honours_override(tmp_path, monkeypatch):
    import prompts
    assert prompts.REFUSAL in prompts.system_prompt()
    alt = tmp_path / 'alt.md'
    alt.write_text('ALT CARD', encoding='utf-8')
    monkeypatch.setenv('CARD_ANSWERER', str(alt))
    assert prompts.system_prompt() == 'ALT CARD'


def test_no_api_key_literals_in_source():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in os.listdir(root):
        if name.endswith('.py'):
            assert 'gsk_' not in open(os.path.join(root, name), encoding='utf-8').read(), name
