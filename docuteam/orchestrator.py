# orchestrator.py
import json, time, uuid
from answering import answer_docs
from config import RELEASE, WORKSPACE
from limited_client import DailyLimit
from llm import ask
from prompts import REFUSAL
from query_cache import cached_answer, store_answer
from router import route_question
from web import research_web

TRACE = WORKSPACE / 'logs' / 'requests.jsonl'

def _result(answer, grounded, sources=()):
    return {'answer': answer, 'grounded': grounded, 'sources': list(sources)}

def handle(question, history=(), urls=()):
    t0, rid = time.time(), uuid.uuid4().hex[:8]
    hit = cached_answer(question, RELEASE)
    if hit:
        res, route = _result(hit, True), 'cache'
    else:
        route = route_question(question)
        try:
            if route == 'chitchat':
                res = _result(ask('answer', 'Reply briefly and politely.', question, tier='big', max_out=150), False)
            elif route == 'out_of_scope':
                res = _result(REFUSAL, False)
            elif route == 'code':
                res = _result('Code tasks use the build workflow (section 5.8).', False)
            elif route == 'web' and urls:
                res = research_web(question, list(urls))
            else:
                res = answer_docs(question, history)
        except DailyLimit as e:
            res = _result('The daily token budget is used up. Try again after the reset (' + str(e) + ').', False)
        if res['grounded']:
            store_answer(question, RELEASE, res['answer'])    # only verified answers are cached
    out = dict(res, route=route, request_id=rid, seconds=round(time.time() - t0, 2))
    with open(TRACE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(dict(out, question=question, release=RELEASE, ts=time.time())) + '\n')
    return out

def find_request(rid):
    for line in open(TRACE, encoding='utf-8'):
        r = json.loads(line)
        if r['request_id'] == rid:
            return r
    return None