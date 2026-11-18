# limited_client.py -- rate-limit-aware LLM client (Chapter 07, Part I)
# Changed for NeuraDocs: a model named hf:<repo> goes to Hugging Face's router, everything else to Groq, and the
# reasoning-effort parameter is only sent to gpt-oss models (other models reject it).
import os
import random
import time


class DailyLimit(Exception):
    """Raised when the daily token budget is used up (a long retry-after, or the local soft cap)."""


_clients = {}


def _get_client(model='openai/gpt-oss-120b'):
    kind = 'hf' if model.startswith('hf:') else 'groq'
    if kind not in _clients:                                  # created lazily so importing this module needs no key
        if kind == 'hf':
            from openai import OpenAI
            _clients[kind] = OpenAI(base_url=os.environ.get('HF_BASE_URL', 'https://router.huggingface.co/v1'), api_key=os.environ['HF_TOKEN'])
        else:
            from groq import Groq
            _clients[kind] = Groq()                           # reads GROQ_API_KEY from the environment; fails if missing
    return _clients[kind]


def call_llm(messages, model='openai/gpt-oss-120b', max_out=1200, effort='low', max_tries=6):
    hf = model.startswith('hf:')
    kw = {'model': model[3:] if hf else model, 'messages': messages}
    if hf:
        kw['max_tokens'] = max_out                            # the router speaks the classic OpenAI protocol
    else:
        kw['max_completion_tokens'] = max_out
        if model.startswith('openai/gpt-oss'):
            kw['reasoning_effort'] = effort
    for attempt in range(max_tries):
        try:
            raw = _get_client(model).chat.completions.with_raw_response.create(**kw)
            try:
                remaining = int(float(raw.headers.get('x-ratelimit-remaining-tokens', '99999')))
            except (TypeError, ValueError):
                remaining = 99999
            if remaining < 1500:
                time.sleep(8)                                 # near the minute limit: let the window recover
            return raw.parse()
        except Exception as e:
            if type(e).__name__ != 'RateLimitError':
                raise
            headers = getattr(getattr(e, 'response', None), 'headers', None) or {}
            wait = float(headers.get('retry-after', 0) or 0) or (2 ** attempt + random.random())
            if wait > 120:                                    # a wait this long means the daily budget is used up
                raise DailyLimit('retry in about ' + str(int(wait)) + ' seconds')
            time.sleep(min(wait, 60))
    raise RuntimeError('rate limit persisted')
