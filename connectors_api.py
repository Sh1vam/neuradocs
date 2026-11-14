# connectors_api.py -- add, list, test and remove connectors (see connectors.py) and serve the Connectors page.
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import connectors

router = APIRouter()


class ConnectorIn(BaseModel):
    name: str
    description: str
    base_url: str
    token_env: str = ''
    token_header: str = 'Authorization'
    token_prefix: str = 'Bearer '
    allow_write: bool = False


class TestIn(BaseModel):
    path: str = '/'


@router.get('/connectors')
def page():
    return FileResponse(Path(__file__).resolve().parent / 'static' / 'connectors.html')


@router.get('/api/connectors')
def list_connectors():
    return {'connectors': [{**c, 'token_set': bool(c['token_env'] and os.environ.get(c['token_env']))} for c in connectors.all_connectors()]}


@router.post('/api/connectors')
def add_connector(body: ConnectorIn):
    try:
        return {'name': connectors.add(body.name, body.description, body.base_url, body.token_env, body.token_header, body.token_prefix, body.allow_write)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete('/api/connectors/{name}')
def delete_connector(name: str):
    try:
        connectors.remove(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {'ok': True}


@router.post('/api/connectors/{name}/test')
def test_connector(name: str, body: TestIn):
    try:
        return {'result': connectors.call(name, 'GET', body.path)[:800]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
