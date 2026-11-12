# build_api.py -- "Build" mode: spec -> multi-file project -> tests in the sandbox -> fix loop -> zip.
# CONCEPTS
#  * Files travel as plain-text blocks, not as JSON tool arguments: code inside JSON needs escaping
#    (quotes, newlines) and models get it wrong. The block markers below cannot clash with code fences.
#  * The fix loop is bounded (MAX_ROUNDS). An unbounded "retry until green" loop burns tokens forever.
#  * Generated code only ever runs inside DocuTeam's Docker sandbox (no network, CPU/memory limits).
#    Without Docker you still get the zip, clearly marked as untested.
import json
import os
import re
import shutil
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

import sandbox_client
import skillset
import store
from llm_client import new_usage

ROOT = Path(__file__).resolve().parent
BUILDS = ROOT / 'docuteam' / 'workspace' / 'code' / 'builds'     # inside the folder the sandbox mounts
router = APIRouter()
_groq, _out, _model, _cost = None, ROOT / 'outputs', 'openai/gpt-oss-120b', None
MAX_FILES, MAX_BYTES, MAX_ROUNDS = 25, 200_000, 3
INSTALL = os.getenv('SANDBOX_INSTALL', '0') == '1'      # pip-install the project's requirements.txt before testing (needs sandbox internet)
SKILL_CHARS = int(os.getenv('SKILL_CHARS', '3000'))     # most one skill adds to the Coder's prompt
TEAM = os.getenv('BUILD_TEAM', '1') != '0'          # Researcher + Planner before the Coder (BUILD_TEAM=0 saves tokens)

SYSTEM = (
    'You are a senior software engineer. Build the project the user describes as a small, runnable Python project.\n'
    'OUTPUT PROTOCOL: reply with ONLY file blocks, each exactly like this:\n\n'
    '=== FILE: relative/path.py ===\n<complete file contents>\n=== END FILE ===\n\n'
    'Rules: always write whole files, never diffs; relative paths only; include README.md, requirements.txt '
    '(only packages that exist in the test sandbox), the source files, and pytest tests in '
    'tests/ (at least 3 meaningful tests that import from the project root). The test sandbox has NO network and only these '
    'packages: Django, Flask, FastAPI, httpx, pytest, pytest-django. For Django use sqlite and include manage.py and a '
    'pytest.ini (DJANGO_SETTINGS_MODULE and pythonpath = .) and test with pytest-django. Keep it small (at most 12 files, '
    'about 350 lines in total); no text outside file blocks.')
FILE_RE = re.compile(r'=== FILE:[ \t]*(\S+?)[ \t]*===\n(.*?)\n=== END FILE ===', re.S)


def configure(groq_client, output_dir, model, cost_fn=None):
    global _groq, _out, _model, _cost
    _groq, _out, _model, _cost = groq_client, Path(output_dir), model, cost_fn


def _with_retries(fn, tries=5):
    # Same idea as docuteam/retry.py: wait out a per-minute limit (free tier: 8,000 tokens per minute).
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:
            if type(e).__name__ != 'RateLimitError' or attempt == tries - 1:
                raise
            headers = getattr(getattr(e, 'response', None), 'headers', None) or {}
            wait = float(headers.get('retry-after', 0) or 0) or 5 * 2 ** attempt
            if wait > 120:                                  # a daily limit: waiting here would only hang the request
                raise
            time.sleep(min(wait, 60))


def _llm(model, flags):
    def call(system, user):
        r = _with_retries(lambda: _groq.chat.completions.create(
            model=model or _model, temperature=0.2, max_tokens=6500,
            extra_body={'reasoning_effort': 'medium'},          # code deserves more thinking than chat
            messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]))
        if getattr(r.choices[0], 'finish_reason', None) == 'length':
            flags['truncated'] = True                   # the last file may be cut off
        return r.choices[0].message.content
    return call


def sandbox_pytest(rel):
    if sandbox_client.configured():                      # online deployment: the sandbox is a separate container
        return sandbox_client.run_folder(BUILDS / Path(rel).name, ['python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider'], 120, install=INSTALL)
    import docs_api
    docs_api._path()
    import sandbox
    name = 'neuradocs-sb'
    cur = sandbox._docker(['inspect', '-f', '{{.Image}}', name])
    img = sandbox._docker(['image', 'inspect', '-f', '{{.Id}}', sandbox.IMAGE])
    if cur.returncode == 0 and img.returncode == 0 and cur.stdout.strip() != img.stdout.strip():
        sandbox._docker(['rm', '-f', name])             # the image was rebuilt: start a container from the new one
    net = sandbox._docker(['inspect', '-f', '{{.HostConfig.NetworkMode}}', name])
    if net.returncode == 0 and net.stdout.strip() != os.environ.get('SANDBOX_NETWORK', 'none'):
        sandbox._docker(['rm', '-f', name])             # SANDBOX_NETWORK changed: recreate with the new network mode
    sandbox.ensure_sandbox(name)
    argv = ['python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', rel]
    if INSTALL and (BUILDS / Path(rel).name / 'requirements.txt').exists():
        rc, out = sandbox.exec_in(name, ['python', '-m', 'pip', 'install', '-r', f'{rel}/requirements.txt', '--target', f'{rel}/.deps', '-q',
                                         '--no-input', '--disable-pip-version-check', '--no-cache-dir', '--retries', '1', '--timeout', '15'], timeout=180)
        if rc:
            return 3, 'pip install failed:\n' + out
        argv = ['env', f'PYTHONPATH={rel}/.deps'] + argv
    return sandbox.exec_in(name, argv, timeout=120)


def _prune(keep=10):                                    # the workspace keeps the newest builds
    dirs = sorted((p for p in BUILDS.glob('*') if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in dirs[keep:]:
        shutil.rmtree(p, ignore_errors=True)


# ---- the team: Researcher -> Planner -> Coder <-> Tester --------------------------------------------------------------
STOP = set('a an the and or of for to with in on that this create build make generate project app application please simple '
           'using use write develop me my i want need new'.split())
PLAN_SYSTEM = ('You are a software architect. Given a request and similar open-source projects, compare three different '
               'implementation options and choose the best. Score each 1-5 for: fit to the request, small enough for at most 12 files, '
               'testable offline with pytest in a sandbox that has only Django, Flask, FastAPI and httpx. Reply with JSON only: '
               '{"options":[{"name":"","approach":"","score":0,"why":""}],"chosen":0,'
               '"spec":"<the final detailed specification for the programmer: stack, file layout, behaviour and a test plan; no code>"}')


def github_search(query, limit=5):
    """Similar projects: GitHub repository search needs no key (60 requests/hour; set GITHUB_TOKEN for more)."""
    headers = {'User-Agent': 'NeuraDocs', 'Accept': 'application/vnd.github+json'}
    if os.getenv('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    url = 'https://api.github.com/search/repositories?' + urllib.parse.urlencode({'q': query, 'sort': 'stars', 'per_page': limit})
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=8) as r:
        items = json.loads(r.read().decode())['items']
    return [{'name': i['full_name'], 'description': (i.get('description') or '')[:140],
             'stars': i['stargazers_count'], 'url': i['html_url']} for i in items]


def research(spec, search):
    words = [w for w in re.findall(r'[a-z0-9]+', spec.lower()) if w not in STOP and len(w) > 2]
    queries = [' '.join(words[:4]) + ' language:python', ' '.join(words[:2]) + ' template language:python'] if words else []
    found, seen = [], set()
    for q in queries:
        for p in search(q):
            if p['name'] not in seen:
                seen.add(p['name'])
                found.append(p)
    return sorted(found, key=lambda p: -p['stars'])[:8]


def plan(spec, found, llm):
    context = '\n'.join(f"- {p['name']} ({p['stars']} stars): {p['description']}" for p in found) or '(none found)'
    raw = llm(PLAN_SYSTEM, f'Request:\n{spec}\n\nSimilar projects:\n{context}')
    try:
        d = json.loads(re.search(r'\{.*\}', raw, re.S).group(0))
        options, chosen = d['options'][:3], int(d['chosen'])
        if not options or not 0 <= chosen < len(options):
            chosen = 0
        return [o for o in options if isinstance(o, dict) and 'name' in o], chosen, str(d['spec'])
    except Exception:                                     # the planner failed: build from the request as written
        return [], 0, spec


def _pytest_summary(out):
    return next((l.strip() for l in reversed(out.splitlines()) if re.search(r'\d+ (passed|failed|error)', l)), 'finished')


def _write(root, text):
    done = []
    for rel, content in FILE_RE.findall(text)[:MAX_FILES]:
        p = (root / rel).resolve()
        if rel.startswith(('/', '\\')) or not p.is_relative_to(root.resolve()) or len(content) > MAX_BYTES:
            continue                                    # path traversal or oversized: skip, never write
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content.rstrip() + '\n', encoding='utf-8')
        done.append(p.relative_to(root.resolve()).as_posix())
    if not done:
        raise ValueError('the model returned no usable file blocks')
    return done


def _skip(p):
    return bool({'__pycache__', '.pytest_cache', '.deps'} & set(p.parts))


def _snapshot(root):
    parts, total = [], 0
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name != 'conftest.py' and not _skip(p) and total < 12000:
            t = p.read_text(encoding='utf-8', errors='replace')[:4000]
            total += len(t)
            parts.append(f'=== FILE: {p.relative_to(root).as_posix()} ===\n{t}\n=== END FILE ===')
    return '\n\n'.join(parts)


def build(spec, model=None, run_tests=None, llm=None, team=None, search=None, emit=None):
    flags, log = {}, []
    run_tests = run_tests or sandbox_pytest
    llm = llm or _llm(model, flags)

    def step(agent, text):
        log.append((agent, text))
        if emit:
            emit(agent, text)

    options, chosen, brief = [], 0, spec
    if TEAM if team is None else team:
        try:
            found = research(spec, search or github_search)
            step('Researcher', f'found {len(found)} similar projects' + (': ' + ', '.join(p['name'] for p in found[:3]) if found else ''))
        except Exception as e:
            found = []
            step('Researcher', f'search unavailable ({type(e).__name__}); continuing without it')
        options, chosen, brief = plan(spec, found, llm)
        step('Planner', f'compared {len(options)} options and chose "{options[chosen]["name"]}"' if options
             else 'no usable plan; building from the request as written')
    bid = uuid.uuid4().hex[:8]
    slug = re.sub(r'[^a-z0-9]+', '-', ' '.join(spec.lower().split()[:4])).strip('-') or 'project'
    root = BUILDS / f'{slug}-{bid}'
    root.mkdir(parents=True)
    # pytest puts a conftest.py's folder on sys.path: that is what lets tests/ import the project files
    (root / 'conftest.py').write_text('# makes the project root importable from tests/\n')
    files, status, out, feedback, rnd = [], 'skipped', '', None, 0
    task = 'Specification:\n' + brief + ('\n\nOriginal request:\n' + spec if brief != spec else '')
    used = skillset.match(spec + ' ' + brief)                    # saved workflows that fit this request (keyword match, no tokens)
    if used:
        step('Skills', 'following ' + ', '.join(s['name'] for s in used))
    system = SYSTEM + ''.join(f'\n\nSkill "{s["name"]}" (follow it):\n{s["body"][:SKILL_CHARS]}' for s in used)
    try:
        for rnd in range(1, MAX_ROUNDS + 1):
            user = task if not feedback else (
                task + '\n\nCurrent files:\n' + _snapshot(root) +
                '\n\nThe tests failed. Fix the code (do not delete or weaken tests). Output every changed file in full.\n\n'
                'Test output:\n' + feedback)
            try:
                done = _write(root, llm(system, user))
            except Exception as e:
                if not files:
                    raise                                # nothing produced yet: report the error
                status, out = 'failed', f'Stopped in round {rnd}: {e}'     # e.g. rate limit: keep the earlier files
                break
            files = sorted(set(files) | set(done))
            step('Coder', f'wrote {len(done)} files' if rnd == 1 else f'fixed the code in round {rnd} ({len(done)} files)')
            try:
                code, out = run_tests('builds/' + root.name)
            except Exception as e:                       # sandbox unavailable or timed out: ship the zip, marked untested
                status, out = 'skipped', str(e)
                step('Tester', 'could not run the tests (reason below)')
                break
            step('Tester', _pytest_summary(out))
            if code == 0:
                status = 'passed'
                break
            status, feedback = 'failed', out[-2000:]
        zip_name = f'{slug}-{bid}.zip'
        _out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(_out / zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(root.rglob('*')):
                if p.is_file() and not _skip(p):
                    z.write(p, slug + '/' + p.relative_to(root).as_posix())
    finally:
        _prune()
    badge = {'passed': 'All tests passed in the sandbox',
             'failed': f'Tests still failing after {rnd} round(s)',
             'skipped': 'Tests were NOT run (sandbox problem, see the output below)'}[status]
    lines = [f'**Built `{slug}`**: {len(files)} files. {badge}.', '']
    if log:
        lines += ['**Team log**'] + [f'{i}. **{a}**: {t}' for i, (a, t) in enumerate(log, 1)] + ['']
    if options:
        lines += ['**Options compared**'] + [f'- {"✓ " if i == chosen else ""}{o["name"]} (score {o.get("score", "?")}): {o.get("why", "")}'
                                              for i, o in enumerate(options)] + ['']
    lines += ['**Files**'] + [f'- `{f}`' for f in files]
    lines += ['', f'Project folder: `docuteam/workspace/code/builds/{root.name}`', f'[Download {slug}.zip](/api/download/{zip_name})']
    if flags.get('truncated'):
        lines += ['', 'The model ran out of output tokens, so a file may be missing. Ask for a smaller project.']
    if out:
        lines += ['', '```', out[-1200:], '```']
    return {'response': '\n'.join(lines), 'zip': zip_name, 'status': status, 'rounds': rnd, 'files': files,
            'log': log, 'options': options}


@router.post('/api/build')
def build_endpoint(request: dict):
    spec = (request.get('message') or '').strip()
    if not spec:
        raise HTTPException(status_code=400, detail='message is required')
    conv_id = request.get('conversation_id')
    if not conv_id or not store.chat_exists(conv_id):
        try:
            conv_id = store.create_chat(request.get('project_id'))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=404, detail='project not found')
    store.add_message(conv_id, 'user', spec)
    usage = new_usage()
    try:
        result = build(spec, request.get('model'))
    except Exception as e:                              # rate limit, no usable files, ...
        store.add_message(conv_id, 'assistant', 'Build failed: ' + str(e))
        raise HTTPException(status_code=500, detail=str(e))
    store.add_message(conv_id, 'assistant', result['response'])
    cost = _cost(usage['prompt'], usage['completion'], request.get('model') or _model) if _cost else 0
    return {'response': result['response'], 'conv_id': conv_id, 'tool_calls': [], 'zip': result['zip'],
            'usage': {**usage, 'cost': cost}}


@router.get('/api/sandbox/status')
def sandbox_state():
    import sandbox_check
    return sandbox_check.status()
