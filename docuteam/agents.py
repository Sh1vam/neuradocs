# agents.py
import os
from pathlib import Path
from agent_core import Agent, Tool
from config import ROOT
from knowledge import retrieve
from tools_basic import approve_cli, read_tool, write_tool
from web import research_web

def card(name):
    override = os.environ.get('CARD_' + name.upper())     # lets weekly.py test a candidate card
    path = Path(override) if override else ROOT / 'roles' / (name + '.md')
    return path.read_text(encoding='utf-8')

STR = {'type': 'string'}

def search_fn(query, k=3):
    return '\n\n'.join('[' + c['id'] + '] ' + c['text'] for c in retrieve(query, k=k))

search_tool = Tool('search_docs', 'Search the private documents. Returns passages with ids.',
    {'type': 'object', 'properties': {'query': STR, 'k': {'type': 'integer'}}, 'required': ['query']},
    search_fn)

web_tool = Tool('research_web', 'Read allowed web pages and return cited facts.',
    {'type': 'object', 'properties': {'question': STR, 'urls': {'type': 'array', 'items': STR}},
     'required': ['question', 'urls']},
    lambda question, urls: research_web(question, urls)['answer'])

AGENTS = {
    'reader': Agent('reader', 'groq-small', card('reader'), [search_tool, read_tool], max_steps=5),
    'web': Agent('web', 'groq-small', card('web'), [web_tool], max_steps=4),
    'writer': Agent('writer', 'groq', card('writer'), [read_tool, write_tool],
                    approve=approve_cli, max_steps=5),
}