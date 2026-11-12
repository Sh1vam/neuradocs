# docs_api.py -- the bridge between NeuraChat (the app) and DocuTeam (grounded document Q&A + sandbox).
# CONCEPT: lazy loading. DocuTeam loads two ML models and a vector DB the moment it is imported
# (10-30 s on CPU). Importing it on first use keeps the chat app's own startup instant.
import re
import shutil
import sys
import tempfile
import threading
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import sandbox_client

ROOT = Path(__file__).resolve().parent
DT = ROOT / 'docuteam'
router = APIRouter()
_lock = threading.Lock()          # one local model copy on CPU: answer one question at a time
_dt = None
_extract = None


def configure(extract):           # NeuraChat's text extractor (pdf, docx, pptx, txt, md), passed in by main.py
    global _extract
    _extract = extract


def _path():
    # DocuTeam uses flat imports (`from config import ...`), so its folder must be importable.
    if str(DT) not in sys.path:
        sys.path.insert(0, str(DT))


def _load():
    global _dt
    if _dt is None:
        _path()
        import config
        import feedback
        import orchestrator
        _dt = SimpleNamespace(handle=orchestrator.handle, find_request=orchestrator.find_request,
                              record=feedback.record_feedback, release=config.RELEASE, ws=config.WORKSPACE)
    return _dt


def ask_docs(question, history=()):
    dt = _load()
    with _lock:
        return dt.handle(question.strip(), history=list(history))


def run_python_sandboxed(code):
    """Run model-written code in DocuTeam's Docker sandbox (no network, CPU/memory limits)."""
    if sandbox_client.configured():                       # online deployment: the sandbox is a separate container
        try:
            rc, out = sandbox_client.run({'snippet.py': code}, ['python', 'snippet.py'], 20)
        except RuntimeError as e:
            return 'Code execution is disabled: ' + str(e)
        return ('exit %d\n%s' % (rc, out))[:2000]
    try:
        _path()
        import sandbox
        snip = DT / 'workspace' / 'code' / '_snippets'
        snip.mkdir(parents=True, exist_ok=True)
        f = snip / (uuid.uuid4().hex[:8] + '.py')
        f.write_text(code, encoding='utf-8')
        try:
            sandbox.ensure_sandbox('neuradocs-sb')
            rc, out = sandbox.exec_in('neuradocs-sb', ['python', '_snippets/' + f.name], timeout=20)
        finally:
            f.unlink(missing_ok=True)
        return ('exit %d\n%s' % (rc, out))[:2000]
    except RuntimeError as e:     # Docker missing or the container could not start
        return 'Code execution is disabled: ' + str(e)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1500)
    history: list[tuple[str, str]] = []


class VoteIn(BaseModel):
    request_id: str
    verdict: Literal['approved', 'rejected']


@router.get('/documents')
def page():
    return FileResponse(ROOT / 'static' / 'documents.html')


@router.get('/api/docs/status')
def status():                     # checks the folders only, so it never triggers the slow model load
    return {'docuteam_present': DT.exists(), 'models_present': (DT / 'models' / 'bge-small-en-v1.5').exists(),
            'index_present': (DT / 'chroma').exists(), 'loaded': _dt is not None}


@router.post('/api/docs/ask')
def ask(body: AskIn):
    try:
        return ask_docs(body.question, [(r, t[:600]) for r, t in body.history[-6:]])
    except Exception as e:        # missing models/index, missing key, rate limit ...
        traceback.print_exc()
        return JSONResponse({'error': type(e).__name__ + ': ' + str(e)}, status_code=500)


@router.post('/api/docs/feedback')
def feedback(body: VoteIn):
    dt = _load()
    rec = dt.find_request(body.request_id)
    if not rec:
        return JSONResponse({'error': 'unknown request id'}, status_code=404)
    dt.record(str(dt.ws / 'logs' / 'feedback.jsonl'), body.request_id, rec['question'], rec['route'],
              dt.release, rec['answer'], body.verdict)
    return {'ok': True}


@router.post('/api/docs/upload')
def upload(file: UploadFile = File(...)):
    """Extract text, save it in DocuTeam's docs folder, and index just that file (chunk, embed, store)."""
    data = file.file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='File too large (max 20 MB)')
    text = _extract(data, file.filename or 'upload')
    if not text.strip() or re.match(r'\[(PDF|DOCX|PPTX|XLSX|XLS|DOC)\b[^\]]*(error|no text layer|not supported|needs)|\[Binary file', text):
        return JSONResponse({'error': 'Could not read any text from this file.'}, status_code=422)
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', Path(file.filename or 'upload').stem)[:60] or 'upload'
    dest = DT / 'workspace' / 'docs' / (name + '.txt')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding='utf-8')
    try:
        _path()
        import knowledge                                  # loads the models on first use
        with _lock, tempfile.TemporaryDirectory() as tmp:
            shutil.copy(dest, tmp)                        # ingest() indexes a whole folder: give it only this file
            chunks = knowledge.ingest(Path(tmp))
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({'error': type(e).__name__ + ': ' + str(e), 'saved': dest.name}, status_code=500)
    return {'ok': True, 'file': dest.name, 'chunks': chunks}
