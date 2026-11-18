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


_effort = contextvars.ContextVar("effort", default=None)


def set_effort(level):
    """The reasoning effort chosen in the page for the current request (gpt-oss models only). Anything else is ignored."""
    _effort.set(level if level in ("low", "medium", "high") else None)


def current_effort():
    return _effort.get()


_hf = None


def _hf_client():
    global _hf
    if _hf is None:
        from openai import OpenAI                                  # Hugging Face's router speaks the OpenAI protocol
        _hf = OpenAI(base_url=os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1"), api_key=os.environ["HF_TOKEN"])
    return _hf


class _Completions:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **kw):
        model = str(kw.get("model", ""))
        if os.getenv("FAKE_LLM") == "1":
            resp = _fake_create(**kw)
        elif model.startswith("hf:"):                              # hf:Qwen/Qwen3-32B -> Hugging Face Inference Providers
            kw = {k: v for k, v in kw.items() if k != "extra_body"}
            kw["model"] = model[3:]
            resp = _hf_client().chat.completions.create(**kw)
        else:
            extra = dict(kw.get("extra_body") or {})
            if model.startswith("openai/gpt-oss"):
                # gpt-oss "thinks" before it answers, and the thinking is billed as output. The page lets you choose how long;
                # without a choice, low keeps answers fast and inside the free tier's tokens-per-minute limit.
                extra.setdefault("reasoning_effort", current_effort() or os.getenv("LLM_EFFORT", "low"))
            else:
                extra.pop("reasoning_effort", None)                # other models reject that parameter
            if extra:
                kw["extra_body"] = extra
            else:
                kw.pop("extra_body", None)
            resp = self._inner.create(**kw)
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
    if 'HF_TOKEN' in text:
        return 'Hugging Face models need HF_TOKEN in .env (a token that may call Inference Providers).'
    if '401' in text or 'invalid api key' in text.lower() or 'unauthorized' in text.lower():
        return 'The provider rejected the API key (401): check GROQ_API_KEY or HF_TOKEN in .env. ' + text[:120]
    if type(e).__name__ == 'RateLimitError' or '429' in text or 'rate limit' in text.lower():
        return ('Groq rate limit reached. The free tier allows about 8,000 tokens per minute and 200,000 per day '
                'for gpt-oss-120b: wait a minute and try again. (' + text[:160] + ')')
    return text
