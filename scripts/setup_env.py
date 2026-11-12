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


def parse(text):
    values = {}
    for line in text.splitlines():
        m = re.match(r'\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$', line)
        if m and not line.lstrip().startswith('#'):
            values[m.group(1)] = m.group(2).strip('"\'')
    return values


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
    o = a.parse_args()
    env = ROOT / '.env'
    existed = env.exists()
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
    print('Next: docker compose ' + ('--profile internet ' if o.internet else '') + 'up -d   (python bootstrap.py does everything)')


if __name__ == '__main__':
    sys.exit(main())
