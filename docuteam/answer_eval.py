# answer_eval.py -- judged answers, rewritten to use ask() (Chapter 03, Part D / Chapter 08, 6.2)
import usage
from llm import ask
from prompts import REFUSAL, build_messages
from team import parse_json
from tokens import trim_to_budget

JUDGE = ('You grade a RAG answer. Reply with JSON only: faithful (0 or 1), correct (0 or 1), reason '
         '(one sentence). faithful means every claim is supported by the context. correct means the '
         'answer agrees with the reference answer.')


def generate(question, chunks):
    msgs = build_messages(question, chunks)
    return ask('answer', msgs[0]['content'], msgs[-1]['content'])


def judge(question, context, answer, reference):
    prompt = ('Question: ' + question + '\n\nContext:\n' + context + '\n\nAnswer: ' + answer +
              '\n\nReference answer: ' + reference)
    return parse_json(ask('review', JUDGE, prompt, max_out=400))


def evaluate_answers(retrieve, evalset, k=3):
    before = usage.today_total()
    answerable = [e for e in evalset if e['answerable']]
    unanswerable = [e for e in evalset if not e['answerable']]
    faithful = correct = refused = 0
    for e in answerable:
        chunks = trim_to_budget(retrieve(e['question'], k), 1500)
        ans = generate(e['question'], chunks)
        ctx = '\n\n'.join('[' + str(i + 1) + '] ' + c['text'] for i, c in enumerate(chunks))
        g = judge(e['question'], ctx, ans, e['reference'])
        faithful += int(g.get('faithful', 0))
        correct += int(g.get('correct', 0))
    for e in unanswerable:
        chunks = trim_to_budget(retrieve(e['question'], k), 1500)
        refused += int(REFUSAL in generate(e['question'], chunks))
    n_tasks = max(len(answerable) + len(unanswerable), 1)
    return {'faithfulness': faithful / max(len(answerable), 1),
            'correctness': correct / max(len(answerable), 1),
            'abstention': refused / max(len(unanswerable), 1),
            'tokens_per_task': (usage.today_total() - before) / n_tasks}
