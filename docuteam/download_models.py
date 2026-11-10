# download_models.py -- run ONCE with internet, so models/ is filled for offline use
from pathlib import Path

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent
snapshot_download('BAAI/bge-small-en-v1.5', local_dir=str(ROOT / 'models' / 'bge-small-en-v1.5'))
snapshot_download('cross-encoder/ms-marco-MiniLM-L-6-v2', local_dir=str(ROOT / 'models' / 'reranker'))
print('models downloaded into', ROOT / 'models')
