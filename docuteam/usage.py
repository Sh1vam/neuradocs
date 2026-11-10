# usage.py
import json, time
from config import WORKSPACE

LOG = WORKSPACE / 'logs' / 'usage.jsonl'

def record(task, tokens):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': time.time(), 'task': task, 'tokens': tokens}) + '\n')

def today_total():
    if not LOG.exists():
        return 0
    start = time.mktime(time.strptime(time.strftime('%Y-%m-%d'), '%Y-%m-%d'))
    return sum(r['tokens'] for r in (json.loads(l) for l in open(LOG, encoding='utf-8')) if r['ts'] >= start)