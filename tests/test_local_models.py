import sys
import types
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

import local_models
import main

client = TestClient(main.app)
HUB_FILES = [NS(rfilename=n, size=10) for n in ('config.json', 'model.safetensors', 'pytorch_model.bin', 'onnx/model.onnx', 'openvino/x.xml', 'vocab.txt', '.gitattributes')]


def fake_hub(monkeypatch, fail=False):
    """A stand-in for huggingface_hub that 'downloads' by writing small files, so no network is needed."""
    calls = []

    class Api:
        def model_info(self, repo, files_metadata=False, token=None):
            return NS(siblings=HUB_FILES)

    def snapshot_download(repo, local_dir, allow_patterns, token=None):
        calls.append((repo, sorted(allow_patterns)))
        if fail:
            raise OSError('no internet')
        for name in allow_patterns:
            p = Path(local_dir) / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'x' * 10)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', types.SimpleNamespace(HfApi=Api, snapshot_download=snapshot_download))
    return calls


@pytest.fixture
def lm(monkeypatch, tmp_path):
    monkeypatch.setattr(local_models, 'MODELS', tmp_path / 'models')
    monkeypatch.setattr(local_models, '_state', {})
    monkeypatch.setenv('AUTO_DOWNLOAD_MODELS', '1')
    return local_models


def test_what_counts_as_present(lm, tmp_path):
    folder = tmp_path / 'models' / 'bge-small-en-v1.5'
    assert lm.status()[0]['status'] == 'missing'
    folder.mkdir(parents=True)
    (folder / 'config.json').write_text('{}')
    assert lm.status()[0]['status'] == 'missing'                        # the weights have not arrived yet
    (folder / 'model.safetensors').write_bytes(b'x')
    assert lm.status()[0]['status'] == 'ready'


def test_only_what_is_needed_is_downloaded(lm, monkeypatch):
    calls = fake_hub(monkeypatch)
    assert lm.ensure_all(log=None, poll=0.01) is True
    assert [c[0] for c in calls].count('BAAI/bge-small-en-v1.5') == 1 and len(calls) == 2
    wanted = calls[0][1]
    assert 'config.json' in wanted and 'model.safetensors' in wanted and 'vocab.txt' in wanted
    assert not any(n in wanted for n in ('pytorch_model.bin', 'onnx/model.onnx', 'openvino/x.xml', '.gitattributes'))   # no duplicate weights or runtimes
    assert all(s['status'] == 'ready' for s in lm.status())


def test_a_model_that_is_already_here_is_not_downloaded_again(lm, monkeypatch, tmp_path):
    folder = tmp_path / 'models' / 'bge-small-en-v1.5'
    folder.mkdir(parents=True)
    (folder / 'config.json').write_text('{}')
    (folder / 'model.safetensors').write_bytes(b'x')
    calls = fake_hub(monkeypatch)
    assert lm.ensure_all(log=None, poll=0.01) is True
    assert [c[0] for c in calls] == ['cross-encoder/ms-marco-MiniLM-L-6-v2']


def test_a_failed_download_is_reported_and_can_be_retried(lm, monkeypatch):
    fake_hub(monkeypatch, fail=True)
    assert lm.ensure_all(log=None, poll=0.01) is False
    st = {s['name']: s for s in lm.status()}
    assert st['embedder']['status'] == 'error' and 'no internet' in st['embedder']['error']
    fake_hub(monkeypatch)
    assert lm.ensure_all(log=None, poll=0.01) is True                    # a second try works (the error state is not sticky)


def test_auto_download_can_be_switched_off(lm, monkeypatch):
    calls = fake_hub(monkeypatch)
    monkeypatch.setenv('AUTO_DOWNLOAD_MODELS', '0')
    assert lm.ensure_all(log=None, poll=0.01) is False and calls == []


def test_progress_follows_the_bytes_on_disk(lm, tmp_path):
    folder = tmp_path / 'models' / 'bge-small-en-v1.5'
    folder.mkdir(parents=True)
    (folder / 'part.incomplete').write_bytes(b'x' * 50)
    lm._state['embedder'] = {'status': 'downloading', 'total': 100, 'error': ''}
    s = lm.status()[0]
    assert s['status'] == 'downloading' and s['progress'] == 0.5


def test_the_registry_matches_docuteams_download_script():
    script = (Path(local_models.ROOT) / 'docuteam' / 'download_models.py').read_text(encoding='utf-8')
    for m in local_models.REGISTRY:
        assert m['repo'] in script and m['dir'] in script, m['name']


def test_models_api_page_and_missing_models_message(lm, monkeypatch):
    calls = fake_hub(monkeypatch)
    names = [m['name'] for m in client.get('/api/local-models').json()['models']]
    assert names == ['embedder', 'reranker'] and 'Download all missing' in client.get('/models').text
    assert client.post('/api/local-models/nope/download').status_code == 404
    r = client.post('/api/docs/ask', json={'question': 'hello'})              # models missing: a clear message, and the download starts
    assert r.status_code == 500 and 'downloading now' in r.json()['error']
