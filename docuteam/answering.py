# answering.py
from check import check_citations           # check_citations from Chapter 05, Part I
from knowledge import retrieve
from llm import ask
from prompts import REFUSAL, build_messages
from query_cache import trim_to_budget

REWRITE = ('Rewrite the last user question as a standalone search query, resolving pronouns using '
           'the conversation. Return only the query.')

def rewrite(history, question):
    if not history:
        return question
    convo = '\n'.join(role + ': ' + text for role, text in list(history)[-6:])
    return ask('route', REWRITE, 'Conversation:\n' + convo + '\n\nLast question: ' + question,
               tier='small', max_out=80).strip()

def answer_docs(question, history=()):
    chunks = trim_to_budget(retrieve(rewrite(history, question), k=6), 1800)
    if not chunks:
        return {'answer': REFUSAL, 'sources': [], 'grounded': False}
    msgs = build_messages(question, chunks)
    ans = ask('answer', msgs[0]['content'], msgs[-1]['content'])
    valid = {str(i + 1) for i in range(len(chunks))}
    check = check_citations(ans, valid)
    grounded = bool(check['cited']) and not check['invalid'] and REFUSAL not in ans
    return {'answer': ans, 'sources': [c['id'] for c in chunks], 'grounded': grounded}