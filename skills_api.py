# skills_api.py -- list, add, approve and delete skills (see skillset.py) and serve the Skills page.
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import skillset

router = APIRouter()


class SkillIn(BaseModel):
    name: str
    description: str
    instructions: str


def _view(s):
    return {'name': s['name'], 'description': s['description'], 'source': s['source']}


@router.get('/skills')
def page():
    return FileResponse(Path(__file__).resolve().parent / 'static' / 'skills.html')


@router.get('/api/skills')
def list_skills():
    return {'skills': [_view(s) for s in skillset.all_skills().values()], 'pending': [_view(s) for s in skillset.list_pending()]}


@router.get('/api/skills/{name}')
def get_skill(name: str, pending: int = 0):
    s = skillset.get_pending(name) if pending else skillset.all_skills().get(name)
    if not s:
        raise HTTPException(status_code=404, detail='no such skill')
    return {**_view(s), 'body': s['body']}


@router.post('/api/skills')
def add_skill(body: SkillIn):
    try:
        return {'name': skillset.save(body.name, body.description, body.instructions)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete('/api/skills/{name}')
def delete_skill(name: str, pending: int = 0):
    try:
        skillset.delete(name, pending=bool(pending))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True}


@router.post('/api/skills/{name}/approve')
def approve_skill(name: str):
    try:
        skillset.approve(name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'ok': True}
