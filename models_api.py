# models_api.py -- the Models page: local models (download them) and the cloud models your keys can use.
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

import local_models

router = APIRouter()


@router.get('/models')
def page():
    return FileResponse(Path(__file__).resolve().parent / 'static' / 'models.html')


@router.get('/api/local-models')
def local_status():
    return {'models': local_models.status(), 'hf_token': bool(os.getenv('HF_TOKEN')), 'auto': os.getenv('AUTO_DOWNLOAD_MODELS', '1') != '0'}


@router.post('/api/local-models/{name}/download')
def download(name: str):
    try:
        return {'started': local_models.start_download(name)}
    except KeyError:
        raise HTTPException(status_code=404, detail='no such local model')
