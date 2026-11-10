# mine_failures.py -- cluster failures so the biggest cause is fixed first (Chapter 06, Part C)
import json


def load_failures(path):
    try:
        rows = [json.loads(line) for line in open(path, encoding='utf-8')]
    except FileNotFoundError:
        return []
    return [r for r in rows if r['verdict'] in ('rejected', 'edited', 'escalated')]


def cluster_failures(rows, k=5):
    from sklearn.cluster import KMeans
    from knowledge import embedder
    texts = [r['reason'] or r['output'][:300] for r in rows]
    vecs = embedder.encode(texts, normalize_embeddings=True)
    km = KMeans(n_clusters=min(k, len(rows)), n_init=10, random_state=0).fit(vecs)
    groups = {}
    for row, label in zip(rows, km.labels_):
        groups.setdefault(int(label), []).append(row)
    return sorted(groups.values(), key=len, reverse=True)   # biggest first
