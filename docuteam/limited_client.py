# limited_client.py -- rate-limit-aware Groq client (Chapter 07, Part I)
import os
import random
import time


class DailyLimit(Exception):
    """Raised when the daily token budget is used up (a long retry-after, or the local soft cap)."""


_client = None

def _get_client():
    global _client
    if _client is None:
        from groq import Groq          # created lazily so importing this module needs no key
        _client = Groq()               # reads GROQ_API_KEY from the environment; fails if missing
    return _client


def call_llm(messages, model='openai/gpt-oss-120b', max_out=1200, effort='low', max_tries=6):
    from groq import RateLimitError
    for attempt in range(max_tries):
        try:
            raw = _get_client().chat.completions.with_raw_response.create(
                model=model, messages=messages,
                max_completion_tokens=max_out, reasoning_effort=effort)
            try:
                remaining = int(float(raw.headers.get('x-ratelimit-remaining-tokens', '99999')))
            except (TypeError, ValueError):
                remaining = 99999
            if remaining < 1500:
                time.sleep(8)            # near the minute limit: let the window recover
            return raw.parse()
        except RateLimitError as e:
            headers = getattr(getattr(e, 'response', None), 'headers', None) or {}
            wait = float(headers.get('retry-after', 0) or 0) or (2 ** attempt + random.random())
            if wait > 120:               # a wait this long means the daily budget is used up
                raise DailyLimit('retry in about ' + str(int(wait)) + ' seconds')
            time.sleep(min(wait, 60))
    raise RuntimeError('rate limit persisted')
