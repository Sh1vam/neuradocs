# query_cache.py -- exact + semantic answer cache (Chapter 07, Part J)
import hashlib
import re
import sqlite3
import time

import numpy as np

from config import WORKSPACE
from tokens import estimate_tokens, trim_to_budget      # re-exported for older imports  # noqa: F401

_db = sqlite3.connect(str(WORKSPACE / 'cache.db'), check_same_thread=False)
_db.execute('create table if not exists exact (k text primary key, answer text, ts real)')
SEM = []        # (vector, answer, timestamp); rebuilt per run, the exact cache persists on disk


def _embed(texts):
    from knowledge import embedder          # imported lazily: loads the local model only when needed
    return embedder.encode(texts, normalize_embeddings=True)


def normalise(q):
    return re.sub(r'\s+', ' ', q.strip().lower())


def key(q, version):
    return hashlib.sha256((version + '|' + normalise(q)).encode()).hexdigest()


def cached_answer(q, version, ttl=86400, threshold=0.93):
    row = _db.execute('select answer, ts from exact where k=?', (key(q, version),)).fetchone()
    if row and time.time() - row[1] < ttl:
        return row[0]
    if SEM:
        sims = np.stack([v for v, _, _ in SEM]) @ _embed([normalise(q)])[0]
        i = int(np.argmax(sims))
        if sims[i] >= threshold and time.time() - SEM[i][2] < ttl:
            return SEM[i][1]
    return None


def store_answer(q, version, answer):
    _db.execute('insert or replace into exact values (?,?,?)', (key(q, version), answer, time.time()))
    _db.commit()
    SEM.append((_embed([normalise(q)])[0], answer, time.time()))
