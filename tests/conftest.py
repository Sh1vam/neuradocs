import os
import sys
import tempfile
from pathlib import Path

import dotenv

# main.py calls load_dotenv() the moment it is imported, so without this line your real .env leaks into every test.
# APP_PASSWORD alone puts the login wall in front of each request (401 "Login required"). Tests never read .env.
dotenv.load_dotenv = lambda *args, **kwargs: False
for name in ('APP_PASSWORD', 'SANDBOX_URL', 'HF_TOKEN', 'GITHUB_TOKEN'):      # ...and a value exported in your shell must not leak either
    os.environ.pop(name, None)

os.environ['NEURACHAT_DB'] = str(Path(tempfile.mkdtemp()) / 'test.db')     # tests never touch your real chats
os.environ.setdefault('GROQ_API_KEY', 'test-key')
os.environ['AUTO_DOWNLOAD_MODELS'] = '0'      # tests never download models
os.environ['BUILD_TEAM'] = '0'          # the team (research + planning) is switched on per test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
