# feedback.py -- capture human verdicts and edits (Chapter 06, Part C)
import json
import time


def record_feedback(path, task_id, task, agent, release, output, verdict,
                    human_edit=None, rating=None, reason=''):
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            'ts': time.time(), 'task_id': task_id, 'task': task, 'agent': agent,
            'release': release, 'output': output, 'verdict': verdict,   # approved, edited, rejected, escalated
            'human_edit': human_edit, 'rating': rating, 'reason': reason,
        }) + '\n')
