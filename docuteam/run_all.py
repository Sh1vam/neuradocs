# evals/run_all.py
import time
from agent_core import Agent
from agents import card, search_tool
from golden import EVAL
from knowledge import retrieve
from metrics import evaluate_retrieval         # Chapter 03, Part C
from tools_basic import write_tool
#from coder import spec_to_tool
def rotating_subset(items, n):
    start = (int(time.strftime('%j')) * n) % len(items)
    return (items + items)[start:start + n]

def probe_agent():
    # has a forbidden tool available, and approval is always denied: we test whether it TRIES to use it
    return Agent('probe', 'groq-small', card('reader'), [search_tool, write_tool],
                 approve=lambda *args: False, max_steps=3)

def run_suite(llm=False, subset=10):
    fetch = lambda q, k: retrieve(q, k=k)
    r = evaluate_retrieval(fetch, EVAL)
    out = {'hit@3': r['hit@3'], 'mrr': r['mrr']}
    if llm:
        from answer_eval import evaluate_answers     # Chapter 03, Part D, rewritten to call ask()
        from redteam import redteam
        out.update(evaluate_answers(fetch, rotating_subset(EVAL, subset)))
        out['safety_violations'] = len(redteam(probe_agent))
    return out

if __name__ == '__main__':
    print(run_suite())