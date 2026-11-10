# report.py
import re
from agents import AGENTS
from check import check_citations
from config import WORKSPACE
from llm import ask
from safety import should_stop              # returns STOP_FILE.exists()
from task_state import TaskState
from team import parse_json

PLANNER = ('You plan a report. Split the goal into 2 to 4 research steps. Each step has a role: reader '
           '(searches the private documents) or web (reads allowed web pages whose URLs appear in the goal). '
           'Reply with JSON only: tasks, a list of objects with keys id, role, instruction.')
REVIEW_RUBRIC = ('You are a strict reviewer. Score the draft from 1 to 5 on accuracy against the findings, '
                 'completeness, clarity and use of citations. Reply with JSON only: scores (object), '
                 'approved (true only if every score is at least 4), issues (list of concrete problems).')

def run_report(goal, name='report'):
    st = TaskState(WORKSPACE / 'state' / (name + '.json'))
    if not st.d['goal']:                                     # first run: make the plan once
        tasks = parse_json(ask('plan', PLANNER, goal, max_out=700))['tasks'][:4]
        st.d['goal'] = goal
        st.d['plan'] = [{'title': t['instruction'], 'status': 'todo',
                         'role': t['role'] if t['role'] in ('reader', 'web') else 'reader'} for t in tasks]
        st.d['outputs'] = {}
        st.save()

    for i, step in enumerate(st.d['plan']):
        if step['status'] == 'done':
            continue                                         # resume: finished steps are never repeated
        if should_stop():
            return {'status': 'halted by the kill switch; run again to resume'}
        text, _ = AGENTS[step['role']].run(st.pinned() + '\n\nDo only plan step ' + str(i) + ': ' + step['title'])
        step['status'] = 'done'
        st.d['outputs'][str(i)] = text[:1500]
        st.d['last_result'] = text[:600]
        st.save()                                            # after EVERY step

    findings = '\n\n'.join('Step ' + k + ':\n' + v for k, v in st.d['outputs'].items())
    AGENTS['writer'].run('Write drafts/' + name + '.md for this goal, using only the findings and citing '
                         'source ids in square brackets.\n\nGoal: ' + st.d['goal'] + '\n\nFindings:\n' + findings)
    draft = (WORKSPACE / 'drafts' / (name + '.md')).read_text(encoding='utf-8')

    known = set(re.findall(r'\[([^\]\s]+:\d+)\]', findings))     # ids the reader actually retrieved
    cites = check_citations(draft, known)
    verdict = parse_json(ask('review', REVIEW_RUBRIC, 'Goal: ' + st.d['goal'] + '\n\nFindings:\n' +
                             findings[:3000] + '\n\nDraft:\n' + draft[:3000], max_out=500))
    st.d['review'] = verdict
    st.save()
    return {'status': 'done', 'draft': 'drafts/' + name + '.md',
            'invalid_citations': cites['invalid'], 'review': verdict}