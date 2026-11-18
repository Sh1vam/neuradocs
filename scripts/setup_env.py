# scripts/setup_env.py -- check your .env and add what is missing. It never changes a value you already set.
#   python scripts/setup_env.py              add missing settings (the two secrets are generated for you)
#   python scripts/setup_env.py --internet   also let the sandbox reach the internet, through the allowlist proxy
import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = {                                  # setting: default. A function generates a secret; None means only you can supply it.
    'GROQ_API_KEY': None,
    'LLM_BIG': 'openai/gpt-oss-120b',
    'APP_PASSWORD': lambda: secrets.token_urlsafe(12),
    'SANDBOX_TOKEN': lambda: secrets.token_urlsafe(24),
    'APP_PORT': '8001',
}
INTERNET = {'SANDBOX_PROXY': 'http://egress:3128', 'SANDBOX_INSTALL': '1'}
SAFE = re.compile(r'^[A-Za-z0-9._:/,@+-]+$')
CHECKED = ('DOMAIN', 'APP_BIND', 'APP_PORT', 'PORT', 'HOST', 'SANDBOX_PROXY', 'EGRESS_ALLOW', 'LLM_BIG', 'LLM_SMALL', 'LLM_VISION')


def problems(values):
    """Values that docker compose or the app cannot use: spaces, quotes, brackets, < > |, or a port that is not a number."""
    found = [f'{k}={v!r}: use a plain value, no spaces, quotes, brackets, < > or |' for k, v in values.items() if k in CHECKED and v and not SAFE.match(v)]
    found += [f'{k}: text after the value ({v[:28]!r}...). Docker reads it as part of the value. Run: python scripts/setup_env.py --fix'
              for k, v in values.items() if k not in SECRET_KEYS and re.search(r'\s{2,}\S', v)]
    if values.get('APP_PORT') and not values['APP_PORT'].isdigit():
        found.append(f"APP_PORT={values['APP_PORT']!r}: must be a number")
    return found


def parse(text):
    values = {}
    for line in text.splitlines():
        m = re.match(r'\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$', line)
        if m and not line.lstrip().startswith('#'):
            values[m.group(1)] = m.group(2).strip('"\'')
    return values


LINE = re.compile(r'^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$')
SECRET_KEYS = {'GROQ_API_KEY', 'HF_TOKEN', 'GITHUB_TOKEN', 'APP_PASSWORD', 'SANDBOX_TOKEN'}        # never touched by --fix
LIST_KEYS = {'EGRESS_ALLOW', 'HF_MODELS'}


def clean(text):
    """Remove explanations written after a value on the same line (docker and dotenv read them as part of the value), stray commas
    in lists, and comment out repeated settings (the last one wins). Secrets are never touched."""
    lines, last = text.splitlines(), {}
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if m and not line.lstrip().startswith('#'):
            last[m.group(1)] = i
    out, changes = [], []
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if not m or line.lstrip().startswith('#'):
            out.append(line)
            continue
        key, value = m.group(1), m.group(2)
        if last[key] != i:
            out.append('# (repeated: the last one wins) ' + line)
            changes.append(f'{key} appeared more than once: the earlier line is commented out (the last one is what docker uses)')
            continue
        if key not in SECRET_KEYS:
            new = re.split(r'\s{2,}|\s#', value, maxsplit=1)[0].strip()
            if key in LIST_KEYS:
                new = ','.join(x.strip() for x in new.split(',') if x.strip())
            if key == 'BUILD_TEAM' and new not in ('0', '1'):
                new = '1'
                changes.append('BUILD_TEAM is a switch (0 or 1), not a count: set to 1')
            elif new != value:
                changes.append(f'{key}: removed the text after the value')
            if new != value:
                line = f'{key}={new}'
        out.append(line)
    return '\n'.join(out) + '\n', changes


def advice(values):
    """Things that work but cost you: not errors, so --fix does not change them."""
    tips = []
    if not values.get('GROQ_API_KEY'):
        tips.append('GROQ_API_KEY is empty: paste your Groq key.')
    if values.get('HF_MODELS') and not values.get('HF_TOKEN'):
        tips.append('HF_MODELS has no effect without HF_TOKEN.')
    if values.get('APP_PASSWORD') and len(values['APP_PASSWORD']) < 10:
        tips.append('APP_PASSWORD is short. Anything that can reach the app, including code running in the sandbox, can guess it: use 12 or more characters.')
    if values.get('LLM_EFFORT') == 'high':
        tips.append('LLM_EFFORT=high spends most of the output budget on thinking: answers can come back empty, and the free tier (about 8,000 tokens a minute) runs out fast. Use low; the page can choose per message.')
    if (values.get('WEB_CONCURRENCY') or '1').isdigit() and int(values.get('WEB_CONCURRENCY') or 1) > 4:
        tips.append('WEB_CONCURRENCY=N starts N app processes, each with its own copy of the models (about 1 GB each). 1 or 2 is plenty.')
    if values.get('SANDBOX_INSTALL') == '1' and not values.get('SANDBOX_PROXY'):
        tips.append('SANDBOX_INSTALL=1 needs the sandbox to reach the internet: set SANDBOX_PROXY=http://egress:3128.')
    if values.get('SANDBOX_NETWORK') == 'bridge':
        tips.append('SANDBOX_NETWORK=bridge gives the local sandbox full internet and LAN access (docker compose does not use it). Remove it.')
    if values.get('HOST') or values.get('PORT'):
        tips.append('HOST and PORT in .env only matter for "python run.py"; docker compose sets them itself.')
    if re.match(r'^[A-Za-z]:[\\/]', values.get('SKILLS_DIR', '')):
        tips.append('SKILLS_DIR is a Windows path and does not exist inside Docker: docker uses the my_skills folder. Remove SKILLS_DIR.')
    return tips


def ensure(path, internet=False, ask_key=False):
    """Fill in what is missing or empty. Returns {setting: value}; a value of None means you must supply it yourself."""
    path = Path(path)
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    have, added = parse(text), {}
    for key, default in {**BASE, **(INTERNET if internet else {})}.items():
        if have.get(key):
            continue                                              # a value you set is never touched
        if default is None:                                       # your API key: only you can supply it
            value = ''
            if ask_key:
                import getpass
                try:
                    value = getpass.getpass('Groq API key (hidden, Enter to skip): ').strip()
                except EOFError:
                    pass
            if not value:
                added[key] = None
                continue
        else:
            value = default() if callable(default) else default
        line = f'{key}={value}'
        if re.search(rf'^{key}=.*$', text, re.M):
            text = re.sub(rf'^{key}=.*$', lambda _: line, text, count=1, flags=re.M)      # an empty KEY= line is filled in
        else:
            text = text.rstrip('\n') + ('\n' if text else '') + line + '\n'
        added[key] = value
    if any(v is not None for v in added.values()):
        path.write_text(text, encoding='utf-8')
    return added


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--internet', action='store_true')
    a.add_argument('--fix', action='store_true', help='clean up explanations after values and repeated settings first')
    o = a.parse_args()
    env = ROOT / '.env'
    existed = env.exists()
    if o.fix and existed:
        cleaned, changes = clean(env.read_text(encoding='utf-8'))
        if changes:
            (ROOT / '.env.bak').write_text(env.read_text(encoding='utf-8'), encoding='utf-8')
            env.write_text(cleaned, encoding='utf-8')
            print('.env cleaned (the old file is in .env.bak):')
            for c in changes:
                print('  - ' + c)
    added = ensure(env, o.internet, ask_key=True)
    print(f'.env {"checked" if existed else "created"}: {env}')
    for key, value in added.items():
        if value is None:
            print(f'  {key} is still empty: open .env and paste your key')
        elif key == 'APP_PASSWORD':
            print(f'  added APP_PASSWORD={value}   <- the web page login (any username, this password)')
        elif key == 'SANDBOX_TOKEN':
            print('  added SANDBOX_TOKEN (a random secret the app and the sandbox service share)')
        else:
            print(f'  added {key}={value}')
    if not added:
        print('  nothing was missing')
    values = parse(env.read_text(encoding='utf-8'))
    for line in problems(values):
        print('  PROBLEM ' + line)
    for line in advice(values):
        print('  NOTE ' + line)
    print('Next: docker compose ' + ('--profile internet ' if o.internet else '') + 'up -d   (python bootstrap.py does everything)')


if __name__ == '__main__':
    sys.exit(main())
