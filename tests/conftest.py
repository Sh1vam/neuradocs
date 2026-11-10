import os
import sys
import tempfile
from pathlib import Path

os.environ['NEURACHAT_DB'] = str(Path(tempfile.mkdtemp()) / 'test.db')     # tests never touch your real chats
os.environ.setdefault('GROQ_API_KEY', 'test-key')
os.environ['BUILD_TEAM'] = '0'          # the team (research + planning) is switched on per test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
