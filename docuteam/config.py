# config.py
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / 'workspace'
for sub in ('docs', 'drafts', 'state', 'logs'):
    (WORKSPACE / sub).mkdir(parents=True, exist_ok=True)

MODELS = {'big': os.environ.get('LLM_BIG', 'openai/gpt-oss-120b'),
          'small': os.environ.get('LLM_SMALL', os.environ.get('LLM_BIG', 'openai/gpt-oss-120b'))}
EFFORT = {'route': 'low', 'extract': 'low', 'answer': 'low',
          'plan': 'medium', 'review': 'medium', 'code': 'medium'}
LIMITS = {'max_input_tokens': 3000, 'max_output_tokens': 1200, 'daily_soft_cap': 180_000}

RELEASE = 'v1'            # change when prompts, models or the index change (it keys the cache)
INDEX_VERSION = 'v1'      # change when the embedder or chunking changes
ALLOWED_WEB = ['docs.python.org', 'en.wikipedia.org']    # start small and add deliberately
STOP_FILE = ROOT / 'STOP'