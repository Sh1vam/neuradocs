# chunkers.py
import re

def chunk_fixed(text, size=120, overlap=20):
    words = text.split()
    step = size - overlap
    out = []
    for start in range(0, len(words), step):
        out.append(' '.join(words[start:start + size]))
        if start + size >= len(words):
            break
    return out

def split_sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

def chunk_sentences(text, max_words=120, overlap_sents=1):
    out, cur, n = [], [], 0
    for s in split_sentences(text):
        w = len(s.split())
        if cur and n + w > max_words:
            out.append(' '.join(cur))
            cur = cur[-overlap_sents:] if overlap_sents else []
            n = sum(len(x.split()) for x in cur)
        cur.append(s)
        n += w
    if cur:
        out.append(' '.join(cur))
    return out

def chunk_recursive(text, max_words=120, seps=('\n\n', '\n', '. ', ' ')):
    text = text.strip()
    if not text:
        return []
    if len(text.split()) <= max_words:
        return [text]
    for i, sep in enumerate(seps):
        parts = text.split(sep)
        if len(parts) > 1:
            break
    else:
        return [text]
    rest = seps[i + 1:] or (' ',)
    out, cur = [], ''
    for p in parts:
        cand = cur + sep + p if cur else p
        if len(cand.split()) <= max_words:
            cur = cand
            continue
        if cur:
            out.append(cur)
            cur = ''
        if len(p.split()) > max_words:
            out.extend(chunk_recursive(p, max_words, rest))
        else:
            cur = p
    if cur:
        out.append(cur)
    return [c.strip() for c in out if c.strip()]

def chunk_by_headers(md, max_words=200):
    sections, title, buf = [], 'intro', []
    for line in md.splitlines():
        if line.startswith('#'):
            if buf:
                sections.append((title, '\n'.join(buf)))
            title, buf = line.lstrip('# ').strip(), []
        else:
            buf.append(line)
    if buf:
        sections.append((title, '\n'.join(buf)))
    out = []
    for title, body in sections:
        for piece in chunk_recursive(body, max_words):
            out.append({'section': title, 'text': title + ': ' + piece})
    return out

def make_chunks(docs, chunker, **kw):
    chunks = []
    for d in docs:
        for j, piece in enumerate(chunker(d['text'], **kw)):
            if isinstance(piece, str):
                piece = {'text': piece, 'section': ''}
            piece.update({'id': d['source'] + ':' + str(j), 'source': d['source']})
            chunks.append(piece)
    return chunks