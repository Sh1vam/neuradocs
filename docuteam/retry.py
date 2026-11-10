# retry.py
import random, time
from limited_client import DailyLimit      # defined in Chapter 07

def with_retries(fn, max_tries=6):
    for attempt in range(max_tries):
        try:
            return fn()
        except Exception as e:
            if type(e).__name__ != 'RateLimitError':
                raise
            headers = getattr(getattr(e, 'response', None), 'headers', None) or {}
            wait = float(headers.get('retry-after', 0) or 0) or (2 ** attempt + random.random())
            if wait > 120:
                raise DailyLimit('retry in about ' + str(int(wait)) + ' seconds')
            time.sleep(min(wait, 60))
    raise RuntimeError('rate limit persisted')