# knowledge.py
import chromadb
import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer
from chunkers import chunk_recursive
from config import INDEX_VERSION, ROOT, WORKSPACE

embedder = SentenceTransformer(str(ROOT / 'models' / 'bge-small-en-v1.5'))
reranker = CrossEncoder(str(ROOT / 'models' / 'reranker'))
db = chromadb.PersistentClient(path=str(ROOT / 'chroma'),
                               settings=chromadb.config.Settings(anonymized_telemetry=False))
col = db.get_or_create_collection('docs_' + INDEX_VERSION, metadata={'hnsw:space': 'cosine'})

def ingest(folder=WORKSPACE / 'docs'):
    total = 0
    for p in sorted(folder.glob('*.*')):
        if p.suffix.lower() not in ('.txt', '.md'):
            continue
        pieces = chunk_recursive(p.read_text(encoding='utf-8'), 120)
        col.delete(where={'source': p.name})            # drop old chunks if the file shrank
        if not pieces:
            continue
        vecs = embedder.encode(pieces, normalize_embeddings=True, batch_size=16)
        col.upsert(ids=[p.name + ':' + str(i) for i in range(len(pieces))], documents=pieces,
                   embeddings=vecs.tolist(), metadatas=[{'source': p.name}] * len(pieces))
        total += len(pieces)
    return total

def retrieve(question, k=4, pool=15):
    qv = embedder.encode([question], normalize_embeddings=True)[0].tolist()
    res = col.query(query_embeddings=[qv], n_results=min(pool, max(col.count(), 1)))
    docs, ids, metas = res['documents'][0], res['ids'][0], res['metadatas'][0]
    if not docs:
        return []
    scores = reranker.predict([(question, d) for d in docs])
    order = np.argsort(scores)[::-1][:k]
    return [{'id': ids[i], 'text': docs[i], 'source': metas[i]['source'], 'score': float(scores[i])}
            for i in order]