# router.py
import numpy as np
from knowledge import embedder
from llm import ask
from team import parse_json

ROUTES = {
    'chitchat': ['hello', 'thanks a lot', 'who are you', 'good morning'],
    'docs': ['what does our policy say about leave', 'how many remote days are allowed',
             'what is the equipment procedure', 'summarise the handbook section on security'],
    'web': ['what does the official documentation say', 'look this up online',
            'what is the latest version of this library'],
    'code': ['write a script that renames files', 'fix this function', 'create a tool that converts csv'],
}
NAMES, EXAMPLES = zip(*[(n, e) for n, exs in ROUTES.items() for e in exs])
EX_VECS = embedder.encode(list(EXAMPLES), normalize_embeddings=True)
VALID = set(ROUTES) | {'out_of_scope'}

ROUTER_PROMPT = ('Classify the message into one route: chitchat, docs (questions about the private '
                 'documents), web (needs public web information), code (build or fix software), '
                 'out_of_scope. Reply with JSON only: route, confidence (0 to 1).')

def route_question(q, threshold=0.75):          # calibrate the threshold on your own queries
    sims = EX_VECS @ embedder.encode([q], normalize_embeddings=True)[0]
    i = int(np.argmax(sims))
    if sims[i] >= threshold:
        return NAMES[i]
    r = parse_json(ask('route', ROUTER_PROMPT, q, tier='big', max_out=100)).get('route')
    return r if r in VALID else 'docs'          # safe default