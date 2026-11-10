# tools_basic.py -- read and write tools confined to the workspace (Chapter 05, Part C)
import json

from agent_core import Tool
from config import WORKSPACE

STR = {'type': 'string'}
ROOT_DIR = WORKSPACE.resolve()
WRITE_DIRS = ('drafts',)           # agents may write ONLY here
HIDDEN_DIRS = ('logs',)            # agents may not read logs (they could tamper with or learn from them)


def _resolve(rel):
    p = (ROOT_DIR / rel).resolve()          # resolve first: expands .. and symlinks
    if not p.is_relative_to(ROOT_DIR):
        raise PermissionError('path outside the workspace')
    return p


def read_file(path):
    p = _resolve(path)
    parts = p.relative_to(ROOT_DIR).parts
    if parts and parts[0] in HIDDEN_DIRS:
        raise PermissionError('that folder is not readable by agents')
    return p.read_text(encoding='utf-8')[:4000]


def write_file(path, content):
    p = _resolve(path)
    parts = p.relative_to(ROOT_DIR).parts
    if not parts or parts[0] not in WRITE_DIRS:
        raise PermissionError('agents may only write inside: ' + ', '.join(WRITE_DIRS))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
    return 'wrote ' + str(len(content)) + ' characters to ' + p.relative_to(ROOT_DIR).as_posix()


read_tool = Tool('read_file', 'Read a text file from the workspace (docs, drafts, state).',
                 {'type': 'object', 'properties': {'path': STR}, 'required': ['path']}, read_file)
write_tool = Tool('write_file', 'Write a text file inside the workspace drafts folder.',
                  {'type': 'object', 'properties': {'path': STR, 'content': STR},
                   'required': ['path', 'content']}, write_file, risk='write')


def approve_cli(agent, tool, args):
    print('APPROVAL NEEDED:', agent, tool.name, json.dumps(args)[:300])
    return input('approve? [y/N] ').strip().lower() == 'y'
