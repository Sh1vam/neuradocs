# store_api.py -- REST routes for projects, chats, pins and messages.
# Mount it in NeuraChat's main.py with two lines:
#     from store_api import router
#     app.include_router(router)
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import store

router = APIRouter(prefix='/api')


class ProjectIn(BaseModel):
    name: str
    instructions: str = ''


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None


class ChatIn(BaseModel):
    project_id: Optional[str] = None
    title: str = 'New chat'


class ChatPatch(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


@router.get('/projects')
def projects():
    return store.list_projects()


@router.post('/projects')
def new_project(body: ProjectIn):
    return {'id': store.create_project(body.name, body.instructions)}


@router.patch('/projects/{pid}')
def edit_project(pid: str, body: ProjectPatch):
    store.update_project(pid, body.name, body.instructions)
    return {'ok': True}


@router.delete('/projects/{pid}')
def remove_project(pid: str):
    store.delete_project(pid)
    return {'ok': True}


@router.get('/chats')
def chats(project_id: Optional[str] = None, q: Optional[str] = None):
    return store.list_chats(project_id, q)


@router.post('/chats')
def new_chat(body: ChatIn):
    try:
        return {'id': store.create_chat(body.project_id, body.title)}
    except sqlite3.IntegrityError:
        raise HTTPException(404, 'project not found')


@router.patch('/chats/{cid}')
def edit_chat(cid: str, body: ChatPatch):
    if body.title is not None:
        store.rename_chat(cid, body.title)
    if body.pinned is not None:
        store.set_pinned(cid, body.pinned)
    return {'ok': True}


@router.delete('/chats/{cid}')
def remove_chat(cid: str):
    store.delete_chat(cid)
    return {'ok': True}


@router.get('/chats/{cid}/messages')
def chat_messages(cid: str):
    return store.get_messages(cid)


@router.get('/storage')
def storage():
    projects, chats = store.counts()
    return {'path': str(store.DB), 'projects': projects, 'chats': chats}


@router.get('/chats/{cid}/build')
def chat_build(cid: str):
    return store.latest_build(cid) or {}
