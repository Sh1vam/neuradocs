# coder.py
import re

from agent_core import Agent, Tool
from agents import STR, card
from autosave import start_autosave        # Chapter 07, Part H
from build_loop import checkpoint          # runs git in the code folder
from config import WORKSPACE
from llm_layer import chat
from sandbox import ensure_sandbox, exec_in

CODE_DIR = WORKSPACE / 'code'              # this folder is what the sandbox mounts at /work
CODE_DIR.mkdir(exist_ok=True)
SANDBOX = 'docuteam-sb'
ALLOWED_IN_SANDBOX = {'python', 'pytest', 'ruff'}

def make_write_code(role):
    def fn(path, content):
        code_root = CODE_DIR.resolve()
        p = (code_root / path).resolve()
        if not p.is_relative_to(code_root):
            raise PermissionError('path outside the code folder')
        rel = p.relative_to(code_root).as_posix()
        name = p.name.lower()
        protected = (rel.lower().startswith('tests/') or name in
                     {'ci_local.py', 'ruff.toml', '.ruff.toml', 'pyproject.toml', 'pytest.ini',
                      'conftest.py', 'setup.cfg', 'tox.ini', '.gitignore'})
        if role == 'coder' and protected:
            raise PermissionError('tests and CI files are read-only for the coder')
        if role == 'tester' and not rel.startswith('tests/'):
            raise PermissionError('the tester may only write tests')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return 'wrote ' + rel
    return fn


def read_code(path):
    p = (CODE_DIR / path).resolve()
    if not p.is_relative_to(CODE_DIR.resolve()):
        raise PermissionError('path outside the code folder')
    if not p.exists():
        return f'(no such file: {path})'
    return p.read_text(encoding='utf-8')[:4000]


def sandbox_run(argv):
    if not argv or argv[0] not in ALLOWED_IN_SANDBOX:
        return 'error: command not allowed'
    ensure_sandbox(SANDBOX)
    code, out = exec_in(SANDBOX, argv, timeout=120)
    return 'exit ' + str(code) + '\n' + out


def write_tool(role):
    # risk 'read': contained (code folder only), git-tracked and reversible, so no per-file approval
    return Tool('write_code', 'Write a file inside the code folder.',
                {'type': 'object', 'properties': {'path': STR, 'content': STR}, 'required': ['path', 'content']},
                make_write_code(role))


read_tool = Tool('read_code', 'Read a file from the code folder.',
                 {'type': 'object', 'properties': {'path': STR}, 'required': ['path']}, read_code)
run_tool = Tool('sandbox_run', 'Run python, pytest or ruff inside the sandbox (no network).',
                {'type': 'object', 'properties': {'argv': {'type': 'array', 'items': STR}}, 'required': ['argv']},
                sandbox_run)


# ---- Coder: plain-text protocol (no code inside JSON tool calls) -------------------------------

FORMAT_RULES = (
    'OUTPUT PROTOCOL (overrides any tool instructions above): you have no tools. Reply only with '
    'the complete contents of each source file you write, in this exact format and nothing else:\n\n'
    'FILE: dates.py\n'
    '```python\n'
    '<complete file contents>\n'
    '```\n\n'
    'Rules: one FILE block per file; always the whole file, never a diff; use ASCII characters only; '
    'indent with 4 spaces; do not write anything under tests/ and do not touch ci_local.py; '
    'the code must pass `ruff check` with no findings.'
)
FILE_RE = re.compile(r'FILE:[ \t]*(\S+)[ \t]*\n```[a-zA-Z]*\n(.*?)\n```', re.S)


def _spec_tests():
    """Test files in tests/, excluding the sanity check."""
    return [f for f in sorted((CODE_DIR / 'tests').glob('test_*.py')) if f.name != 'test_sanity.py']


def _tests_text():
    return '\n\n'.join(f'--- tests/{f.name} ---\n' + f.read_text(encoding='utf-8')[:6000]
                       for f in _spec_tests())


def _sources_text():
    parts = [f'--- {f.name} ---\n' + f.read_text(encoding='utf-8')[:4000]
             for f in sorted(CODE_DIR.glob('*.py')) if f.name != 'ci_local.py']
    return '\n\n'.join(parts) or '(no source files yet)'


def coder_round(spec, feedback=None):
    """One LLM call -> parse FILE blocks -> write them. Returns a list of result strings."""
    msg = ('Implement the specification so that every test passes.\n\nSpec: ' + spec +
           '\n\nTests (read-only):\n' + _tests_text() +
           '\n\nCurrent source files:\n' + _sources_text())
    if feedback:
        msg += '\n\nThe last check run failed. Fix the code, not the tests.\n\nOutput:\n' + feedback
    system = card('coder') + '\n\n' + FORMAT_RULES
    out = chat('groq', system, [{'role': 'user', 'text': msg}])
    blocks = FILE_RE.findall(out['text'])
    notes = FILE_RE.sub('', out['text']).strip()
    if notes:
           print('coder notes:', notes[:500])
    if not blocks:
        return ['no FILE blocks found in the reply']
    write = make_write_code('coder')
    results = []
    for path, content in blocks:
        try:
            results.append(write(path, content.rstrip() + '\n'))
        except PermissionError as e:
            results.append(f'blocked {path}: {e}')
    return results

def autofix():
    """Sort imports (a safe, mechanical fix) so LLM rounds go to logic, not cosmetics."""
    exec_in(SANDBOX, ['ruff', 'check', '--fix', '--select', 'I', '--exit-zero', '.'], timeout=60)


def spec_to_tool(spec, max_rounds=4, skip_tests=False):
    """Tester writes tests -> you approve -> coder implements until ci_local.py is green.

    skip_tests=True reuses the tests already in tests/ (approved earlier), so no tokens are
    spent on the tester and no approval prompt is shown.
    """
    ensure_sandbox(SANDBOX)
    stop = start_autosave(300)
    try:
        if skip_tests:
            if not _spec_tests():
                print('skip_tests=True but no test files found in tests/; run once without it.')
                return False
            autofix()                       # tidies the already-approved test file's import order
        else:
            tester = Agent('tester', 'groq', card('tester'),
                           [write_tool('tester'), read_tool], max_steps=5)
            tester.run('Write pytest tests in tests/ for this specification. Cover normal cases, edge '
                       'cases and errors.\n\nSpec: ' + spec)
            autofix()                       # so you approve (and commit) the cleaned version
            for f in _spec_tests():
                print('---', f.name, '---')
                print(f.read_text(encoding='utf-8')[:4000])
            if input('Approve these tests? [y/N] ').strip().lower() != 'y':
                return False
            checkpoint('tests approved')

        feedback = None
        for i in range(max_rounds):
            print(f'round {i + 1}:', coder_round(spec, feedback))
            autofix()                       # fixes import order in the coder's file too
            code, out = exec_in(SANDBOX, ['python', 'ci_local.py'], timeout=300)
            if code == 0:
                checkpoint('green: ' + spec[:50])
                return True
            print(out[-1500:])
            feedback = out[-1500:]
        return False                        # still failing: a human takes over
    finally:
        stop.set()