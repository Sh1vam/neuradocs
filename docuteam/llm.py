# llm.py -- the only function that talks to the model (Chapter 08, Milestone 1)
import os
import time

import usage
from config import EFFORT, LIMITS, MODELS
from limited_client import DailyLimit, call_llm
from tokens import estimate_tokens

# Task-aware fakes, so routing, planning and review still parse when USE_FAKE_LLM is set.
FAKES = {
    'route': '{"route": "docs", "confidence": 0.9}',
    'extract': '{"facts": [], "relevant": false}',
    'plan': '{"tasks": [{"id": 1, "role": "reader", "instruction": "Search the documents."}]}',
    'review': '{"scores": {}, "approved": true, "issues": [], "faithful": 1, "correct": 1, "reason": "fake"}',
}


def ask(task, system, user, tier='big', max_out=None):
    if os.environ.get('USE_FAKE_LLM'):                 # tests and load tests: no quota used
        time.sleep(0.5)
        return FAKES.get(task, 'FAKE ANSWER [1]')
    est = estimate_tokens(system) + estimate_tokens(user)
    if est > LIMITS['max_input_tokens']:
        raise ValueError('prompt too large (' + str(est) + ' tokens): trim the context')
    if usage.today_total() > LIMITS['daily_soft_cap']:
        raise DailyLimit('local daily soft cap reached')
    resp = call_llm([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                    model=MODELS[tier], max_out=max_out or LIMITS['max_output_tokens'],
                    effort=EFFORT[task])
    usage.record(task, resp.usage.total_tokens)
    text = resp.choices[0].message.content or ''
    if not text:
        raise ValueError('empty reply: reasoning may have used the output cap; raise max_out')
    return text
