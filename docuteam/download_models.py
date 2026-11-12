# download_models.py -- run ONCE with internet, so models/ is filled for offline use
from pathlib import Path
import os
from huggingface_hub import snapshot_download
from dotenv import load_dotenv

load_dotenv()
HF_TOKEN = os.environ.get("HF_TOKEN")  # set this in your environment (see .env.example) or replace with your token string
ROOT = Path(__file__).resolve().parent
try:
    snapshot_download('BAAI/bge-small-en-v1.5', local_dir=str(ROOT / 'models' / 'bge-small-en-v1.5'), token=HF_TOKEN)
    snapshot_download('cross-encoder/ms-marco-MiniLM-L-6-v2', local_dir=str(ROOT / 'models' / 'reranker'), token=HF_TOKEN)
except Exception as e:
    print("Error downloading models:", e)
    print("Make sure you have set the HF_TOKEN environment variable correctly.")
    snapshot_download('BAAI/bge-small-en-v1.5', local_dir=str(ROOT / 'models' / 'bge-small-en-v1.5'))
    snapshot_download('cross-encoder/ms-marco-MiniLM-L-6-v2', local_dir=str(ROOT / 'models' / 'reranker'))
print('models downloaded into', ROOT / 'models')
