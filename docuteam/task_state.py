# task_state.py -- the state file that survives interruptions (Chapter 07, Part I)
import json
import os
import time
from pathlib import Path


class TaskState:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.d = json.loads(self.path.read_text(encoding='utf-8'))
        else:
            self.d = {'goal': '', 'constraints': [], 'plan': [], 'decisions': [],
                      'last_result': '', 'next_action': ''}

    def save(self):
        self.d['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.d, indent=2), encoding='utf-8')
        os.replace(tmp, self.path)          # atomic: a reset never leaves a half-written file

    def pinned(self, max_result_chars=800):
        lines = ['GOAL: ' + self.d['goal']]
        if self.d['constraints']:
            lines.append('CONSTRAINTS: ' + '; '.join(self.d['constraints']))
        lines.append('PLAN:')
        for i, s in enumerate(self.d['plan']):
            lines.append('  ' + str(i) + '. [' + s['status'] + '] ' + s['title'])
        if self.d['decisions']:
            lines.append('DECISIONS: ' + '; '.join(self.d['decisions'][-8:]))
        lines.append('LAST RESULT: ' + self.d['last_result'][:max_result_chars])
        lines.append('NEXT ACTION: ' + self.d['next_action'])
        return '\n'.join(lines)

    def apply(self, u):                      # u: a model's JSON update
        i = int(u.get('step_index', -1))
        if 0 <= i < len(self.d['plan']) and u.get('status') in ('todo', 'doing', 'done', 'blocked'):
            self.d['plan'][i]['status'] = u['status']
        if u.get('decision'):
            self.d['decisions'].append(str(u['decision'])[:200])
        self.d['last_result'] = str(u.get('last_result', ''))[:600]
        self.d['next_action'] = str(u.get('next_action', ''))[:300]
