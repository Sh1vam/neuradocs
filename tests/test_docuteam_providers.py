from types import SimpleNamespace as NS

import pytest

import docs_api


class Raw:
    headers = {}

    def parse(self):
        return 'parsed'


@pytest.fixture
def calls(monkeypatch):
    docs_api._path()
    import limited_client
    seen = []
    stub = NS(chat=NS(completions=NS(with_raw_response=NS(create=lambda **kw: seen.append(kw) or Raw()))))
    monkeypatch.setattr(limited_client, '_get_client', lambda model='': stub)
    return seen


def test_gpt_oss_gets_the_effort_parameter_and_other_models_do_not(calls):
    import limited_client
    assert limited_client.call_llm([], model='openai/gpt-oss-120b', max_out=100, effort='low') == 'parsed'
    limited_client.call_llm([], model='llama-3.3-70b-versatile', max_out=100, effort='low')
    assert calls[0]['reasoning_effort'] == 'low' and calls[0]['max_completion_tokens'] == 100
    assert 'reasoning_effort' not in calls[1]                                     # other models reject it


def test_hugging_face_models_use_the_classic_parameters(calls):
    import limited_client
    limited_client.call_llm([], model='hf:Qwen/Qwen3-32B', max_out=100, effort='low')
    assert calls[0]['model'] == 'Qwen/Qwen3-32B' and calls[0]['max_tokens'] == 100
    assert 'reasoning_effort' not in calls[0] and 'max_completion_tokens' not in calls[0]


def test_docuteams_role_providers_follow_the_same_rules():
    docs_api._path()
    import llm_layer
    base = {'kind': 'openai', 'model': 'x', 'base_url': 'https://api.groq.com/openai/v1', 'key': 'GROQ_API_KEY', 'effort': 'low', 'max_out': 3000}
    assert llm_layer._route(dict(base, model='openai/gpt-oss-20b'))['effort'] == 'low'
    assert 'effort' not in llm_layer._route(dict(base, model='llama-3.3-70b-versatile'))
    hf = llm_layer._route(dict(base, model='hf:Qwen/Qwen3-32B'))
    assert hf['model'] == 'Qwen/Qwen3-32B' and hf['key'] == 'HF_TOKEN' and 'huggingface' in hf['base_url'] and 'effort' not in hf
