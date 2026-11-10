# scripts/integrity_check.py -- is the project consistent and safe to ship?
#   python scripts/integrity_check.py [--zip neuradocs.zip] [--db path/to/neurachat.db]
# Exit code 1 if any check FAILs. Also runs as a test: tests/test_integrity.py.
import argparse
import ast
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {'node_modules', '__pycache__', '.pytest_cache', 'data', 'outputs', 'models', 'chroma', 'logs', 'state'}
TEXT = {'.py', '.md', '.txt', '.json', '.html', '.js', '.yml', '.yaml', '.sh', '.cfg', '.ini', '.toml', '.lock', '.example', ''}
SECRETS = [re.compile(p) for p in (r'gsk_[A-Za-z0-9]{20,}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'AKIA[0-9A-Z]{16}')]
ALIAS = {'docx': 'python-docx', 'pptx': 'python-pptx', 'dotenv': 'python-dotenv', 'multipart': 'python-multipart', 'PIL': 'pillow',
         'sklearn': 'scikit-learn', 'yaml': 'pyyaml', 'sentence_transformers': 'sentence-transformers', 'PyPDF2': 'pypdf2',
         'starlette': 'fastapi', 'fastapi': 'fastapi', 'pydantic': 'pydantic', 'uvicorn': 'uvicorn', 'chromadb': 'chromadb'}


OPTIONAL = {'anthropic'}          # a provider DocuTeam imports only when you select it


def norm(name):
    return re.sub(r'[-_.]+', '-', name.lower())


def project_files(root):
    for p in sorted(root.rglob('*')):
        if p.is_file() and not SKIP & set(p.relative_to(root).parts):
            yield p


def check(root=ROOT, zip_path=None, db=None):
    res = []
    add = lambda level, msg: res.append((level, msg))           # noqa: E731
    files = list(project_files(root))
    rel = lambda p: p.relative_to(root).as_posix()               # noqa: E731

    # 1. secrets: nothing that looks like a key or private key in any text file
    hits = [rel(p) for p in files if p.suffix in TEXT and p.stat().st_size < 1_000_000
            and any(s.search(p.read_text(encoding='utf-8', errors='ignore')) for s in SECRETS)]
    add('FAIL' if hits else 'PASS', f'secrets in source files: {hits}' if hits else 'no API keys or private keys in any text file')
    if (root / '.env').exists():
        add('WARN', '.env exists (fine on your machine, but it must never be zipped, committed or baked into an image)')

    # 2. git metadata: docuteam/workspace/code must be a plain folder, and there must be no nested repositories
    nested = [rel(p) for p in root.rglob('.git*') if not SKIP & set(p.relative_to(root).parts)
              and p.name not in ('.gitignore', '.gitattributes') or (p.name in ('.gitignore', '.gitkeep') and 'workspace/code' in p.as_posix())]
    nested += [rel(p) for p in root.rglob('.gitmodules')]
    add('FAIL' if nested else 'PASS', f'git metadata that should not be there: {sorted(set(nested))}' if nested
        else 'no .git, .gitmodules or stray .gitignore: docuteam/workspace/code is a plain folder')

    # 3. every Python file parses
    broken = []
    for p in (q for q in files if q.suffix == '.py'):
        try:
            ast.parse(p.read_text(encoding='utf-8', errors='replace'))
        except SyntaxError as e:
            broken.append(f'{rel(p)}:{e.lineno}')
    add('FAIL' if broken else 'PASS', f'syntax errors: {broken}' if broken else f'{sum(1 for p in files if p.suffix == ".py")} Python files parse')

    # 4. every third-party import is covered by requirements.txt
    req = {norm(re.split(r'[<>=!~\[; ]', l.strip())[0]) for l in (root / 'requirements.txt').read_text().splitlines() if l.strip() and not l.startswith('#')}
    local = {p.stem for p in files if p.suffix == '.py' and p.parent in (root, root / 'docuteam')} | {d.name for d in (root / 'docuteam').iterdir() if d.is_dir()}
    missing = set()
    for p in (q for q in files if q.suffix == '.py' and 'tests' not in q.parts):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8', errors='replace'))):
            names = [a.name.split('.')[0] for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module and not node.level else []
            for n in names:
                if n not in sys.stdlib_module_names and n not in local and n not in OPTIONAL and norm(ALIAS.get(n, n)) not in req:
                    missing.add(n)
    add('WARN' if missing else 'PASS', f'imports not listed in requirements.txt (maybe optional): {sorted(missing)}' if missing
        else 'every third-party import is listed in requirements.txt')

    # 5. the pages only call routes that exist
    if 'main' not in sys.modules:
        os.environ.setdefault('GROQ_API_KEY', 'integrity-check')
        os.environ.setdefault('NEURACHAT_DB', str(Path(tempfile.mkdtemp()) / 'check.db'))
        sys.path.insert(0, str(root))
    import main
    paths = list(main.app.openapi()['paths'])           # also lists routes added with include_router
    routes = [re.sub(r'\{[^}]+\}', '[^/]+', x) for x in paths]
    prefixes = [re.sub(r'\{[^}]+\}', '', x) for x in paths]
    unknown = []
    for page in (root / 'static').glob('*.html'):
        for lit in set(re.findall(r'''(?:\}|['"`])(/api/[^'"`\s$?]*)''', page.read_text(encoding='utf-8'))):
            if not any(re.fullmatch(r, lit) for r in routes) and not (lit.endswith('/') and any(x.startswith(lit) for x in prefixes)):
                unknown.append(f'{page.name}: {lit}')
    add('FAIL' if unknown else 'PASS', f'pages call routes that do not exist: {unknown}' if unknown
        else f'every /api call in the pages matches one of the {len(routes)} routes')

    # 6. Docker and compose files point at things that exist
    problems = []
    for df in [root / 'Dockerfile', root / 'runner' / 'Dockerfile']:
        for line in df.read_text().splitlines():
            if line.startswith('COPY') and '--from' not in line:
                for src in line.split()[1:-1]:
                    if not (root / src).exists() and src != '.':
                        problems.append(f'{df.name}: COPY {src}')
    compose = (root / 'docker-compose.yml').read_text()
    example = (root / '.env.example').read_text()
    for var in set(re.findall(r'\$\{([A-Z_]+):\?', compose)):
        if var not in example:
            problems.append(f'compose needs {var} but .env.example does not mention it')
    for sh in root.glob('*.sh'):
        if b'\r' in sh.read_bytes():
            problems.append(f'{sh.name} has Windows line endings (the container cannot run it)')
    add('FAIL' if problems else 'PASS', f'deployment files: {problems}' if problems else 'Dockerfiles, compose file and entrypoint are consistent')

    # 7. every requirement is pinned by the constraints file
    cons = {norm(re.split(r'[<>=!~\[; @]', l.strip())[0]) for l in (root / 'constraints.txt').read_text().splitlines() if l.strip() and not l.startswith('#')}
    unpinned = sorted(r for r in req if r not in cons)
    add('WARN' if unpinned else 'PASS', f'requirements without a pinned version: {unpinned}' if unpinned else 'every requirement has a pinned version')

    # 8. optional: a database and a zip file
    if db:
        con = sqlite3.connect(db)
        bad = con.execute('pragma integrity_check').fetchone()[0]
        orphans = con.execute('select count(*) from messages where chat_id not in (select id from chats)').fetchone()[0]
        add('PASS' if bad == 'ok' and not orphans else 'FAIL', f'database integrity_check: {bad}, orphan messages: {orphans}')
    if zip_path:
        z = zipfile.ZipFile(zip_path)
        names = z.namelist()
        forbidden = [n for n in names if re.search(r'(^|/)(\.env|\.git[^/]*|\.gitmodules|__pycache__|data|outputs|node_modules)(/|$)', n)
                     and not n.endswith(('.gitignore', '.gitattributes'))]
        add('FAIL' if z.testzip() else 'PASS', 'zip file CRC check' + (f' failed at {z.testzip()}' if z.testzip() else ': every file reads back correctly'))
        add('FAIL' if forbidden else 'PASS', f'zip contains files that must not ship: {forbidden[:5]}' if forbidden else f'zip contents are clean ({len(names)} files)')
        top = {n.split('/')[0] for n in names}
        on_disk = {rel(p) for p in files if p.name not in ('.env',)}
        absent = sorted(on_disk - {n.split('/', 1)[1] for n in names if '/' in n})[:5]
        add('WARN' if absent else 'PASS', f'files on disk but not in the zip: {absent}' if absent else 'zip matches the project folder')
    return res


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('--zip')
    a.add_argument('--db')
    o = a.parse_args()
    results = check(ROOT, o.zip, o.db)
    for level, msg in results:
        print(f'{level:5} {msg}')
    fails = sum(1 for level, _ in results if level == 'FAIL')
    print(f'\n{len(results)} checks: {sum(1 for l, _ in results if l == "PASS")} passed, {sum(1 for l, _ in results if l == "WARN")} warnings, {fails} failed')
    sys.exit(1 if fails else 0)
