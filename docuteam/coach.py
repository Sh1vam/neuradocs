# coach.py -- proposes small, reviewable role-card edits (Chapter 06, Part C)
from llm import ask
from team import parse_json

COACH = (
    'You improve the role card of an AI agent. Given the current role card and a group of similar failures '
    'with reviewer notes, propose the smallest edits that would prevent them. Reply with JSON only: '
    'edits, a list of objects with keys old, new, reason. Each old must be copied exactly from the card, '
    'or be empty to append new at the end.'
)


def apply_edits(card, edits):
    for e in edits:
        if e['old']:
            if card.count(e['old']) != 1:
                continue                      # skip missing or ambiguous edits
            card = card.replace(e['old'], e['new'])
        else:
            card = card.rstrip() + '\n' + e['new'] + '\n'
    return card


def propose_card(card, failure_group, provider='groq'):
    # `provider` is kept for compatibility with the chapter; DocuTeam routes through ask() so the
    # call is token-guarded and counted.
    notes = '\n'.join('- ' + (r['reason'] or 'no note') for r in failure_group[:10])
    msg = 'Current role card:\n' + card + '\n\nFailures:\n' + notes
    edits = parse_json(ask('plan', COACH, msg, max_out=700))['edits']
    return apply_edits(card, edits)
