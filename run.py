# run.py -- start NeuraDocs:  python run.py   (set PORT=8010 if port 8001 is busy)
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
from sandbox_check import status as sandbox_status  # noqa: E402

dt = Path('docuteam')
sb = sandbox_status()
checks = [
    ('GROQ_API_KEY', bool(os.getenv('GROQ_API_KEY')), 'copy .env.example to .env and paste your key'),
    ('DocuTeam models', (dt / 'models' / 'bge-small-en-v1.5').exists() and (dt / 'models' / 'reranker').exists(),
     'copy your models/ folder into docuteam/ or run: python docuteam/download_models.py'),
    ('DocuTeam index', (dt / 'chroma').exists(), 'copy your chroma/ folder into docuteam/ or run: python docuteam/cli.py ingest'),
    ('Docker sandbox', sb['ok'], sb['reason'] + '  (needed for Build tests and run_python)'),
]
print('Preflight')
for name, ok, fix in checks:
    print(('  ok       ' if ok else '  MISSING  ') + name + ('' if ok else '  ->  ' + fix))
import store  # noqa: E402

projects, chats = store.counts()
print(f'  Chats are saved in {store.DB}  ({projects} projects, {chats} chats)')
if chats == 0:
    print('  Chats from another copy of the project? Stop the server and copy that copy\'s data/neurachat.db to the path above.')
if not os.getenv('GROQ_API_KEY'):
    sys.exit('Cannot start without GROQ_API_KEY.')
Path('outputs').mkdir(exist_ok=True)

import uvicorn  # noqa: E402

port = int(os.getenv('PORT', '8001'))
host = os.getenv('HOST', '127.0.0.1')
if host != '127.0.0.1' and not os.getenv('APP_PASSWORD'):
    sys.exit('Refusing to listen on a public address without APP_PASSWORD in .env.')
print(f'\nNeuraDocs  chat: http://127.0.0.1:{port}   documents Q&A: /documents   API docs: /docs')
uvicorn.run('main:app', host=host, port=port, workers=int(os.getenv('WEB_CONCURRENCY', '1')))   # >1 = more processes, each loads the models
