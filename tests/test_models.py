import contextvars
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

import llm_client
import main
import models_registry

client = TestClient(main.app)


def stub(record, tag):
    def create(**kw):
        record.append((tag, kw))
        return NS(choices=[NS(message=NS(content='ok', tool_calls=None))], usage=NS(prompt_tokens=1, completion_tokens=1))
    return NS(chat=NS(completions=NS(create=create)))


def test_hugging_face_models_go_to_the_hf_router(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_client, '_hf_client', lambda: stub(calls, 'hf'))
    ad = llm_client.GroqAdapter(stub(calls, 'groq'))
    ad.chat.completions.create(model='hf:Qwen/Qwen3-32B', messages=[], extra_body={'reasoning_effort': 'low'})
    ad.chat.completions.create(model='openai/gpt-oss-20b', messages=[])
    assert calls[0][0] == 'hf' and calls[0][1]['model'] == 'Qwen/Qwen3-32B' and 'extra_body' not in calls[0][1]
    assert calls[1][0] == 'groq' and calls[1][1]['extra_body'] == {'reasoning_effort': 'low'}


def test_the_effort_chosen_in_the_page_is_used_and_other_models_never_get_it():
    calls = []
    ad = llm_client.GroqAdapter(stub(calls, 'groq'))

    def run():                                                   # a copied context, so the choice does not leak into other tests
        llm_client.set_effort('high')
        ad.chat.completions.create(model='openai/gpt-oss-120b', messages=[])
        llm_client.set_effort('extreme')                         # not a level: back to the default
        ad.chat.completions.create(model='openai/gpt-oss-120b', messages=[])
        ad.chat.completions.create(model='llama-3.3-70b-versatile', messages=[], extra_body={'reasoning_effort': 'high'})
    contextvars.copy_context().run(run)
    assert calls[0][1]['extra_body']['reasoning_effort'] == 'high'
    assert calls[1][1]['extra_body']['reasoning_effort'] == 'low'
    assert 'extra_body' not in calls[2][1]


def test_model_list_merges_live_groq_and_hugging_face_models(monkeypatch):
    def fake_get(url, token):
        if 'groq' in url:
            return {'data': [{'id': 'openai/gpt-oss-20b', 'active': True, 'context_window': 131072}, {'id': 'whisper-large-v3', 'active': True},
                             {'id': 'meta-llama/llama-prompt-guard-2-86m', 'active': True}]}
        return {'data': [{'id': 'Qwen/Qwen3-32B'}]}
    monkeypatch.setattr(models_registry, '_get', fake_get)
    monkeypatch.setattr(models_registry, '_cache', {'at': 0.0, 'models': {}})
    monkeypatch.setenv('HF_TOKEN', 'hf_test')
    monkeypatch.delenv('HF_MODELS', raising=False)
    models = client.get('/api/models').json()['models']
    assert models['openai/gpt-oss-120b']['kind'] == 'chat' and models['openai/gpt-oss-20b']['provider'] == 'groq'
    assert models['whisper-large-v3']['kind'] == 'audio' and models['meta-llama/llama-prompt-guard-2-86m']['kind'] == 'guard'
    assert models['hf:Qwen/Qwen3-32B']['provider'] == 'huggingface' and models['hf:Qwen/Qwen3-32B']['name'] == 'Qwen3-32B (HF)'


def test_an_hf_shortlist_needs_no_lookup(monkeypatch):
    called = []
    monkeypatch.setattr(models_registry, '_get', lambda *a: called.append(a) or {})
    monkeypatch.setattr(models_registry, '_cache', {'at': 0.0, 'models': {}})
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.setenv('HF_TOKEN', 'hf_test')
    monkeypatch.setenv('HF_MODELS', 'Qwen/Qwen3-32B, other/model')
    found = models_registry.live({})
    assert set(found) == {'hf:Qwen/Qwen3-32B', 'hf:other/model'} and not called


def test_key_errors_say_which_key():
    assert 'HF_TOKEN' in llm_client.friendly_error(KeyError('HF_TOKEN'))
    assert 'GROQ_API_KEY' in llm_client.friendly_error(RuntimeError('Error code: 401 - Invalid API Key'))
