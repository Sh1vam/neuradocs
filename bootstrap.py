# bootstrap.py -- from a fresh machine to a running, sandboxed app:  python bootstrap.py   (needs Docker with Compose v2)
import base64
import getpass
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def sh(*cmd, check=True):
    print('>', ' '.join(cmd), flush=True)
    return subprocess.run(cmd, check=check)


def main():
    if not shutil.which('docker'):
        sys.exit('Docker is required: https://docs.docker.com/get-docker/')
    if sh('docker', 'compose', 'version', check=False).returncode:
        sys.exit('Docker Compose v2 is required.')
    env = Path('.env')
    if not env.exists():
        key, password = getpass.getpass('Groq API key (hidden): ').strip(), secrets.token_urlsafe(12)
        env.write_text(f'GROQ_API_KEY={key}\nLLM_BIG=openai/gpt-oss-120b\nAPP_PASSWORD={password}\n'
                       f'SANDBOX_TOKEN={secrets.token_urlsafe(24)}\n')
        print(f'Created .env. Web login: any username, password {password}')
    values = dict(l.split('=', 1) for l in env.read_text().splitlines() if '=' in l and not l.startswith('#'))
    sh('docker', 'compose', 'build')                  # requirements, models and the sandbox service are built here
    sh('docker', 'compose', 'run', '--rm', '--no-deps', '--entrypoint', 'python', 'app', '-m', 'pytest', 'tests', '-q')
    sh('docker', 'compose', 'up', '-d')
    port = values.get('APP_PORT', '8001')
    print('Waiting for the app (the first start builds the document index)...', flush=True)
    for _ in range(90):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3)
            break
        except Exception:
            time.sleep(2)
    else:
        sys.exit('The app did not become healthy: run "docker compose logs app"')
    token = base64.b64encode(f'u:{values.get("APP_PASSWORD", "")}'.encode()).decode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}/api/sandbox/status', headers={'Authorization': 'Basic ' + token})
    print('Sandbox:', urllib.request.urlopen(req, timeout=10).read().decode())
    print(f'Ready: http://127.0.0.1:{port}  (HTTPS on your domain: set DOMAIN in .env, then docker compose --profile tls up -d)')


if __name__ == '__main__':
    main()
