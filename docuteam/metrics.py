# metrics.py -- retrieval metrics (Chapter 03, Part C). Costs no API tokens.
def evaluate_retrieval(retrieve, evalset, ks=(1, 3, 5)):
    items = [e for e in evalset if e['answerable']]
    hits = {k: 0 for k in ks}
    rr_sum, misses = 0.0, []
    for e in items:
        results = retrieve(e['question'], max(ks))          # chunk dicts, best first
        rank = None
        for i, c in enumerate(results):
            if e['must_contain'].lower() in c['text'].lower():
                rank = i + 1
                break
        for k in ks:
            if rank is not None and rank <= k:
                hits[k] += 1
        rr_sum += 1.0 / rank if rank else 0.0
        if rank is None:
            misses.append(e['question'])
    n = max(len(items), 1)
    out = {'hit@' + str(k): hits[k] / n for k in ks}
    out['mrr'] = rr_sum / n
    out['misses'] = misses
    return out
