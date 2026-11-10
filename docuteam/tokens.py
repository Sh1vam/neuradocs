# tokens.py -- cheap token estimates (no model needed, so importing it is fast)
def estimate_tokens(text):
    return len(text) // 4 + 1


def trim_to_budget(chunks, max_tokens):
    kept, used = [], 0
    for c in chunks:
        t = estimate_tokens(c['text'])
        if used + t > max_tokens:
            break
        kept.append(c)
        used += t
    return kept
