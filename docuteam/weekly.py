# weekly.py
import os
from coach import propose_card                   # Chapter 06, Part C
from config import ROOT, WORKSPACE
from run_all import run_suite
from gate import gate
from mine_failures import cluster_failures, load_failures

FEEDBACK = WORKSPACE / 'logs' / 'feedback.jsonl'
CARD_FOR_ROUTE = {'docs': 'answerer', 'chitchat': 'answerer', 'web': 'web'}

def to_gate(m):
    return {'success': m.get('correctness', m['hit@3']),
            'safety_violations': m.get('safety_violations', 0),
            'cost_per_task': m.get('tokens_per_task', 0)}

def main():
    rows = load_failures(str(FEEDBACK))
    if len(rows) < 5:
        print('only', len(rows), 'failures logged; collect more feedback first')
        return
    group = cluster_failures(rows, k=min(4, len(rows)))[0]          # biggest cluster first
    name = CARD_FOR_ROUTE.get(group[0]['agent'], 'answerer')         # the agent field holds the route
    current = (ROOT / 'roles' / (name + '.md')).read_text(encoding='utf-8')
    cand_path = ROOT / 'roles' / (name + '_candidate.md')
    cand_path.write_text(propose_card(current, group, provider='groq'), encoding='utf-8')

    base = to_gate(run_suite(llm=True))
    os.environ['CARD_' + name.upper()] = str(cand_path)             # test the candidate card
    new = to_gate(run_suite(llm=True))
    del os.environ['CARD_' + name.upper()]

    ok, why = gate(new, base)
    print('candidate', 'PASSES' if ok else 'FAILS', '-', why)
    print('baseline', base)
    print('candidate', new)
    # If it passes: read the diff yourself, rename the candidate into place, bump RELEASE in config.py.

if __name__ == '__main__':
    main()