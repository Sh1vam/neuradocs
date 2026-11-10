# agent_core.py -- Tool and Agent (Chapter 05, Part C) with the DocuTeam safety wiring
import json
import time

import usage
from config import LIMITS, WORKSPACE
from limited_client import DailyLimit
from llm_layer import chat
from safety import should_stop

TRACE = WORKSPACE / 'logs' / 'traces.jsonl'
RESULT_CAP = 2000          # characters of any tool result that reach the model


class Tool:
    def __init__(self, name, description, schema, fn, risk='read'):
        self.name, self.description, self.schema, self.fn, self.risk = name, description, schema, fn, risk

    def spec(self):
        return {'name': self.name, 'description': self.description, 'schema': self.schema}


class Agent:
    def __init__(self, name, provider, system, tools=(), max_steps=5, approve=None, log=None):
        self.name, self.provider, self.system = name, provider, system
        self.tools = {t.name: t for t in tools}
        self.max_steps, self.approve, self.log = max_steps, approve, log

    def execute(self, call):
        tool = self.tools.get(call['name'])
        if tool is None:
            return 'error: unknown tool ' + str(call['name'])
        if tool.risk != 'read':
            if not (self.approve and self.approve(self.name, tool, call['args'])):
                return 'error: action not approved'
        try:
            return str(tool.fn(**call['args']))[:RESULT_CAP]
        except Exception as e:                      # errors become observations the model can react to
            return 'error: ' + type(e).__name__ + ': ' + str(e)

    def _trace(self, task, outcome, tokens, started, tr):
        try:
            with open(TRACE, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'ts': time.time(), 'agent': self.name, 'provider': self.provider,
                                    'task': task[:300], 'outcome': outcome, 'tokens': tokens,
                                    'seconds': round(time.time() - started, 2), 'messages': tr}) + '\n')
        except OSError:
            pass

    def run(self, task):
        started, tokens = time.time(), 0
        tr = [{'role': 'user', 'text': task}]
        specs = [t.spec() for t in self.tools.values()] or None
        outcome = 'step_limit'
        try:
            for step in range(self.max_steps):
                if should_stop():
                    outcome = 'killed'
                    return 'STOPPED: kill switch', tr
                if usage.today_total() > LIMITS['daily_soft_cap']:
                    outcome = 'daily_cap'
                    raise DailyLimit('local daily soft cap reached')
                out = chat(self.provider, self.system, tr, specs)
                tokens += out.get('tokens', 0)
                usage.record('agent:' + self.name, out.get('tokens', 0))
                tr.append({'role': 'assistant', 'text': out['text'], 'calls': out['calls']})
                if not out['calls']:
                    outcome = 'done'
                    return out['text'], tr
                for c in out['calls']:
                    res = self.execute(c)
                    if self.log:
                        self.log({'agent': self.name, 'step': step, 'tool': c['name'],
                                  'args': c['args'], 'result': res[:200]})
                    tr.append({'role': 'tool', 'id': c['id'], 'name': c['name'], 'result': res})
            return 'STOPPED: step limit reached.', tr
        finally:
            self._trace(task, outcome, tokens, started, tr)
