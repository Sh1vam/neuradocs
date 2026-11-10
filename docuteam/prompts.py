# prompts.py -- grounding prompts (Chapter 04). The system prompt now lives in roles/answerer.md
# and is read at CALL time, so the weekly loop can test a candidate card (env var CARD_ANSWERER).
import os
from pathlib import Path

from config import ROOT

REFUSAL = 'I could not find this in the provided documents.'


def system_prompt():
    override = os.environ.get('CARD_ANSWERER')
    path = Path(override) if override else ROOT / 'roles' / 'answerer.md'
    return path.read_text(encoding='utf-8').strip()


def build_messages(question, chunks, examples=None):
    context = '\n\n'.join('[' + str(i + 1) + '] ' + c['text'] for i, c in enumerate(chunks))
    user = (
        '<context>\n' + context + '\n</context>\n\n'
        'Question: ' + question + '\n'
        'Answer in at most three sentences with citations.'
    )
    msgs = [{'role': 'system', 'content': system_prompt()}]
    for q, a in (examples or []):          # few-shot examples as past turns
        msgs += [{'role': 'user', 'content': q}, {'role': 'assistant', 'content': a}]
    msgs.append({'role': 'user', 'content': user})
    return msgs
