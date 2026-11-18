# local_models.py -- the models this app runs ON YOUR MACHINE (not through an API): which ones, whether they are here, downloading them.
# Cloud models (Groq, Hugging Face Inference Providers) run on the provider's servers: nothing to download for those.
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / 'docuteam' / 'models'                 # where DocuTeam looks for them (see docuteam/download_models.py)
REGISTRY = [
    {'name': 'embedder', 'repo': 'BAAI/bge-small-en-v1.5', 'dir': 'bge-small-en-v1.5', 'size_mb': 135,
     'purpose': 'Turns text into vectors, so documents can be searched by meaning'},
    {'name': 'reranker', 'repo': 'cross-encoder/ms-marco-MiniLM-L-6-v2', 'dir': 'reranker', 'size_mb': 90,
     'purpose': 'Re-reads the best passages together with the question and keeps the most relevant'},
]
SKIP_DIRS = ('onnx/', 'openvino/', 'tf/', 'flax/', 'rust/', 'coreml/')
SKIP_EXT = ('.onnx', '.msgpack', '.h5', '.ot', '.tflite', '.mlmodel', '.gguf')
_state, _lock = {}, threading.Lock()                   # name -> {'status': 'downloading' | 'error', 'total': bytes, 'error': text}


def present(folder):
    folder = Path(folder)
    return (folder / 'config.json').is_file() and ((folder / 'model.safetensors').is_file() or (folder / 'pytorch_model.bin').is_file())


def folder_bytes(folder):
    return sum(f.stat().st_size for f in Path(folder).rglob('*') if f.is_file()) if Path(folder).is_dir() else 0


def _pick(files):
    """Only what the app needs: no ONNX, OpenVINO, TensorFlow or Flax copies, and the weights once, not twice."""
    keep = [f for f in files if not f.rfilename.startswith(SKIP_DIRS + ('.',)) and not f.rfilename.endswith(SKIP_EXT)]
    if any(f.rfilename == 'model.safetensors' for f in keep):
        keep = [f for f in keep if f.rfilename != 'pytorch_model.bin']
    return keep


def status():
    out = []
    for m in REGISTRY:
        folder, st = MODELS / m['dir'], _state.get(m['name'], {})
        if present(folder) and st.get('status') != 'downloading':
            s, p = 'ready', 1.0
        elif st.get('status') == 'downloading':
            s, p = 'downloading', min(0.99, folder_bytes(folder) / max(st.get('total') or 1, 1)) if st.get('total') else 0.0
        elif st.get('status') == 'error':
            s, p = 'error', 0.0
        else:
            s, p = 'missing', 0.0
        out.append({**m, 'status': s, 'progress': round(p, 3), 'error': st.get('error', '')})
    return out


def _download(m):
    try:
        from huggingface_hub import HfApi, snapshot_download
        token = os.getenv('HF_TOKEN') or None
        files = _pick(HfApi().model_info(m['repo'], files_metadata=True, token=token).siblings)
        _state[m['name']]['total'] = sum(f.size or 0 for f in files)
        snapshot_download(m['repo'], local_dir=str(MODELS / m['dir']), allow_patterns=[f.rfilename for f in files], token=token)
        _state.pop(m['name'], None)
    except Exception as e:                              # no internet, rate limit, disk full ...
        _state[m['name']] = {'status': 'error', 'error': f'{type(e).__name__}: {e}'[:300], 'total': 0}


def start_download(name):
    """Begin downloading one model in the background. False when it is already here or already downloading."""
    m = next((x for x in REGISTRY if x['name'] == name), None)
    if m is None:
        raise KeyError(name)
    with _lock:
        if present(MODELS / m['dir']) or _state.get(name, {}).get('status') == 'downloading':
            return False
        _state[name] = {'status': 'downloading', 'total': 0, 'error': ''}
    threading.Thread(target=_download, args=(m,), daemon=True).start()
    return True


def start_missing():
    return [m['name'] for m in REGISTRY if start_download(m['name'])]


def ensure_all(log=print, poll=3.0):
    """Download whatever is missing and wait for it. True when every model is ready. AUTO_DOWNLOAD_MODELS=0 only reports."""
    if os.getenv('AUTO_DOWNLOAD_MODELS', '1') != '0':
        start_missing()
        while True:
            busy = [s for s in status() if s['status'] == 'downloading']
            if not busy:
                break
            if log:
                log('  downloading: ' + ', '.join(f"{s['name']} {int(s['progress'] * 100)}%" for s in busy))
            time.sleep(poll)
    return all(s['status'] == 'ready' for s in status())
