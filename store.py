# store.py -- persistence for a Claude-style chat app: projects, chats, pinned chats, messages.
# WHY SQLite: a real database in one file that ships with Python and survives restarts.
# (NeuraChat keeps chats in a plain dict, so every restart wipes them.)
import os
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

# The database lives in your home folder, not in the project folder: unzipping a new copy of the project
# (or moving it) must not leave your chats behind. Override with NEURACHAT_DB.
LEGACY = Path(__file__).resolve().parent / 'data' / 'neurachat.db'      # where earlier versions kept it
DEFAULT_DB = Path.home() / '.neuradocs' / 'neurachat.db'
DB = Path(os.environ.get('NEURACHAT_DB') or DEFAULT_DB)

SCHEMA = '''
create table if not exists projects (
  id text primary key, name text not null, instructions text not null default '', created real not null);
create table if not exists chats (
  id text primary key,
  project_id text references projects(id) on delete cascade,   -- NULL = chat outside any project
  title text not null, pinned integer not null default 0, created real not null, updated real not null);
create table if not exists messages (
  id integer primary key autoincrement,
  chat_id text not null references chats(id) on delete cascade,
  role text not null, content text not null, created real not null);
create table if not exists builds (
  id integer primary key autoincrement,
  chat_id text not null references chats(id) on delete cascade,
  folder text not null, slug text not null, zip text not null, created real not null);
create index if not exists idx_builds_chat on builds(chat_id, id);
create index if not exists idx_chats_project on chats(project_id, pinned, updated);
create index if not exists idx_messages_chat on messages(chat_id, id);
'''


@contextmanager
def db():
    # One short-lived connection per call: FastAPI runs sync handlers in several threads, and a
    # sqlite3 connection must not be shared between threads. SQLite also ignores foreign keys
    # (and so "on delete cascade") unless every connection switches them on.
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('pragma foreign_keys = on')
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB == DEFAULT_DB and not DB.exists() and LEGACY.exists():
        shutil.copy2(LEGACY, DB)             # first run with the new location: bring the old chats along
    with db() as con:
        con.execute('pragma journal_mode = wal')       # readers and the writer no longer block each other
        con.executescript(SCHEMA)


def counts():
    with db() as con:
        return (con.execute('select count(*) from projects').fetchone()[0],
                con.execute('select count(*) from chats').fetchone()[0])


def _id():
    return uuid.uuid4().hex[:12]


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


# ---- projects: a named workspace whose "instructions" apply to every chat inside it ----
def create_project(name, instructions=''):
    pid = _id()
    with db() as con:
        con.execute('insert into projects values (?,?,?,?)',
                    (pid, name.strip() or 'Untitled project', instructions, time.time()))
    return pid


def list_projects():
    with db() as con:
        return _rows(con.execute('select * from projects order by created desc'))


def update_project(pid, name=None, instructions=None):
    with db() as con:
        if name is not None:
            con.execute('update projects set name=? where id=?', (name.strip() or 'Untitled project', pid))
        if instructions is not None:
            con.execute('update projects set instructions=? where id=?', (instructions, pid))


def delete_project(pid):                       # cascades to its chats and their messages
    with db() as con:
        con.execute('delete from projects where id=?', (pid,))


# ---- chats ----
def create_chat(project_id=None, title='New chat'):
    cid, now = _id(), time.time()
    with db() as con:                          # raises IntegrityError if project_id does not exist
        con.execute('insert into chats values (?,?,?,?,?,?)', (cid, project_id, title, 0, now, now))
    return cid


def list_chats(project_id=None, q=None):
    sql, args = 'select * from chats where 1=1', []
    if project_id:
        sql += ' and project_id=?'
        args.append(project_id)
    if q:                                      # search titles and message text; escape LIKE wildcards
        like = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        sql += (" and (title like ? escape '\\' or id in "
                "(select chat_id from messages where content like ? escape '\\'))")
        args += [like, like]
    sql += ' order by pinned desc, updated desc'      # pinned chats first, then most recent
    with db() as con:
        return _rows(con.execute(sql, args))


def chat_exists(cid):
    with db() as con:
        return con.execute('select 1 from chats where id=?', (cid,)).fetchone() is not None


def set_pinned(cid, pinned):
    with db() as con:
        con.execute('update chats set pinned=? where id=?', (1 if pinned else 0, cid))


def rename_chat(cid, title):
    with db() as con:
        con.execute('update chats set title=? where id=?', (title.strip() or 'New chat', cid))


def delete_chat(cid):
    with db() as con:
        con.execute('delete from chats where id=?', (cid,))


# ---- builds: the project folder made in a chat, so a later "fix it" can load the same code ----
def add_build(chat_id, folder, slug, zip_name):
    with db() as con:
        con.execute('insert into builds (chat_id, folder, slug, zip, created) values (?,?,?,?,?)', (chat_id, folder, slug, zip_name, time.time()))


def latest_build(chat_id):
    with db() as con:
        row = con.execute('select folder, slug, zip, created from builds where chat_id=? order by id desc limit 1', (chat_id,)).fetchone()
    return dict(row) if row else None


# ---- messages ----
def add_message(chat_id, role, content):
    now = time.time()
    with db() as con:
        cur = con.execute('insert into messages (chat_id, role, content, created) values (?,?,?,?)',
                          (chat_id, role, content, now))
        con.execute('update chats set updated=? where id=?', (now, chat_id))
        if role == 'user':                     # the first user message becomes the chat title
            con.execute("update chats set title=? where id=? and title='New chat'",
                        (' '.join(content.split())[:50] or 'New chat', chat_id))
        return cur.lastrowid


def get_messages(chat_id, last=None):          # last=10 -> only the newest 10 (what you send the LLM)
    with db() as con:
        rows = _rows(con.execute('select role, content, created from messages where chat_id=? order by id',
                                 (chat_id,)))
    return rows[-last:] if last else rows


def system_prompt_for(chat_id, base):
    # Project instructions are simply appended to the system prompt of every chat in the project.
    with db() as con:
        row = con.execute('select p.instructions from chats c join projects p on p.id = c.project_id '
                          'where c.id=?', (chat_id,)).fetchone()
    if row and row['instructions'].strip():
        return base + '\n\nProject instructions:\n' + row['instructions'].strip()
    return base


if __name__ == '__main__':                     # python store.py   -> runs on a throw-away database
    import tempfile
    DB = Path(tempfile.mkdtemp()) / 'selftest.db'
    init()
    p = create_project('Thesis', 'Answer formally.')
    a, b = create_chat(p), create_chat()
    add_message(a, 'user', 'Explain RAG')
    add_message(b, 'user', 'hello')
    set_pinned(b, True)
    assert [c['id'] for c in list_chats()] == [b, a]             # pinned first
    assert [c['id'] for c in list_chats(project_id=p)] == [a]
    assert [c['id'] for c in list_chats(q='rag')] == [a]         # search finds the chat by its text
    assert 'Answer formally.' in system_prompt_for(a, 'Base')
    delete_project(p)
    assert [c['id'] for c in list_chats()] == [b]                # cascade removed chat a
    print('store.py self-test passed')
else:
    init()
