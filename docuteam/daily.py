# daily.py
import json, time
import usage
from config import LIMITS, WORKSPACE

def main():
    midnight = time.mktime(time.strptime(time.strftime('%Y-%m-%d'), '%Y-%m-%d'))
    rows = [json.loads(l) for l in open(WORKSPACE / 'logs' / 'requests.jsonl', encoding='utf-8')]
    today = [r for r in rows if r['ts'] >= midnight]
    refusals = sum('could not find' in r['answer'] for r in today)
    print('requests', len(today), '| refusals', refusals, '| cache hits', sum(r['route'] == 'cache' for r in today))
    print('tokens today', usage.today_total(), 'of soft cap', LIMITS['daily_soft_cap'])
    print('slow (over 30 s):', sum(r['seconds'] > 30 for r in today))

if __name__ == '__main__':
    main()