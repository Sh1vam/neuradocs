# llm_client.py -- the one place every Groq call passes through: model-specific settings and readable errors.
import contextvars
import os
import time
from types import SimpleNamespace as NS

_usage = contextvars.ContextVar("usage", default=None)
_hook = None


def new_usage():
    """Start counting tokens for the current request. Every non-streamed call made while serving it,
    including calls inside tools and worker threads that copied the context, adds to the returned dict."""
    u = {"prompt": 0, "completion": 0}
    _usage.set(u)
    return u


def set_usage_hook(fn):          # fn(prompt, completion, model): feeds the sidebar totals
    global _hook
    _hook = fn


def _fake_create(**kw):
    """FAKE_LLM=1: a stand-in model for load tests, so stress tests spend no tokens. FAKE_LLM_DELAY = seconds per reply."""
    delay, words = float(os.getenv('FAKE_LLM_DELAY', '1.0')), ('This is a simulated reply used for load testing. ' * 3).split(' ')
    if kw.get('stream'):
        def gen():
            for w in words:
                time.sleep(delay / len(words))           # a blocking wait, like the network read of a real stream
                yield NS(choices=[NS(delta=NS(content=w + ' '))])
        return gen()
    time.sleep(delay)
    return NS(choices=[NS(message=NS(content=' '.join(words), tool_calls=None), finish_reason='stop')],
              usage=NS(prompt_tokens=50, completion_tokens=40))


class _Completions:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **kw):
        if str(kw.get('model', '')).startswith('openai/gpt-oss'):
            # gpt-oss "thinks" before it answers, and the thinking is billed as output. A low effort keeps
            # answers fast and inside the free tier's tokens-per-minute limit. A caller can still override it.
            kw.setdefault('extra_body', {}).setdefault('reasoning_effort', os.getenv('LLM_EFFORT', 'low'))
        resp = _fake_create(**kw) if os.getenv("FAKE_LLM") == "1" else self._inner.create(**kw)
        u, usage = _usage.get(), getattr(resp, "usage", None)
        if u is not None and usage is not None and not kw.get("stream"):
            p, c = usage.prompt_tokens or 0, usage.completion_tokens or 0
            u["prompt"] += p
            u["completion"] += c
            if _hook:
                _hook(p, c, kw.get("model", ""))
        return resp


class _Chat:
    def __init__(self, inner):
        self.completions = _Completions(inner.completions)


class GroqAdapter:
    def __init__(self, client):
        self._client = client
        self.chat = _Chat(client.chat)

    def __getattr__(self, name):
        return getattr(self._client, name)


def friendly_error(e):
    text = str(e)
    if type(e).__name__ == 'RateLimitError' or '429' in text or 'rate limit' in text.lower():
        return ('Groq rate limit reached. The free tier allows about 8,000 tokens per minute and 200,000 per day '
                'for gpt-oss-120b: wait a minute and try again. (' + text[:160] + ')')
    return text
