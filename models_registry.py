# models_registry.py -- which models can the page offer? The known ones plus what your keys can really use (live lists).
import json
import os
import time
import urllib.request

_cache = {'at': 0.0, 'models': {}}


def _get(url, token):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token, 'User-Agent': 'NeuraDocs'})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode())


def kind(model_id):
    m = model_id.lower()
    if any(w in m for w in ('whisper', 'orpheus', 'tts')):
        return 'audio'                                          # speech models: not for chat
    if 'guard' in m:
        return 'guard'                                          # safety classifiers: not for chat
    return 'chat'


def _entry(model_id, provider, context=None):
    label = model_id.split('/')[-1] + (' (HF)' if provider == 'huggingface' else '')
    return {'name': label, 'context_window': context or 131072, 'supports_vision': False, 'kind': kind(model_id), 'provider': provider,
            'description': 'Hugging Face Inference Providers' if provider == 'huggingface' else 'Groq'}


def live(known):
    """The known models plus everything your keys can use right now. Cached for 10 minutes; a failed lookup just means fewer entries."""
    if time.time() - _cache['at'] < 600 and _cache['models']:
        return {**known, **_cache['models']}
    found = {}
    key = os.getenv('GROQ_API_KEY')
    if key:
        try:
            for m in _get('https://api.groq.com/openai/v1/models', key).get('data', []):
                if m.get('active', True) and m['id'] not in known:
                    found[m['id']] = _entry(m['id'], 'groq', m.get('context_window'))
        except Exception:
            pass
    token = os.getenv('HF_TOKEN')
    if token:
        shortlist = [x.strip() for x in os.getenv('HF_MODELS', '').split(',') if x.strip()]    # HF_MODELS=Qwen/Qwen3-32B,... skips the lookup
        try:
            ids = shortlist or sorted(m['id'] for m in _get(os.getenv('HF_BASE_URL', 'https://router.huggingface.co/v1') + '/models', token).get('data', []))
            for mid in ids[:int(os.getenv('HF_MODELS_MAX', '60'))]:
                found['hf:' + mid] = _entry(mid, 'huggingface', 32768)
        except Exception:
            pass
    _cache.update(at=time.time(), models=found)
    return {**known, **found}
