# skillset.py -- skills: reusable instructions and workflows that make the agent and the builder act the same way every time.
# A skill is a folder with a SKILL.md: a front-matter block (name, description) followed by the instructions.
# PROGRESSIVE DISCLOSURE: only name + description are always in the prompt; the full text is loaded when a skill is used.
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUNDLED = ROOT / 'skills'                                  # shipped with the app
NAME = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')            # also what keeps a name from escaping its folder
MAX_BODY = 8000
STOP = set('a an the and or of for to with in on that this is it be by as at from into can you your my me i we our '
           'create build make generate write please simple using use asked when new want need do does how what'.split())


EXTRA_KEYWORDS = {                                   # more words that should find a skill whose own text we do not edit (it is third-party)
    'frontend-design': 'website web page landing ui interface frontend dashboard html css layout styling design',
}


def user_dir():
    import store                                           # your skills live next to your chats (the Docker data volume)
    return Path(os.environ.get('SKILLS_DIR') or store.DB.parent / 'skills')


def parse(text):
    m = re.match(r'---\s*\n(.*?)\n---\s*\n?(.*)', text, re.S)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2).strip()


def _read(path, source):
    try:
        parsed = parse(Path(path).read_text(encoding='utf-8'))
    except OSError:
        return None
    if not parsed:
        return None
    meta, body = parsed
    name = meta.get('name', '')
    if name != Path(path).parent.name or not NAME.match(name) or not meta.get('description') or not body:
        return None
    return {'name': name, 'description': meta['description'][:400], 'body': body, 'source': source}


def _scan(base, source):
    found = {}
    if base.is_dir():
        for d in sorted(base.iterdir()):
            if d.is_dir() and not d.name.startswith('_') and (d / 'SKILL.md').is_file():
                s = _read(d / 'SKILL.md', source)
                if s:
                    found[s['name']] = s
    return found


def all_skills():
    skills = _scan(BUNDLED, 'bundled')
    skills.update(_scan(user_dir(), 'user'))               # a skill of yours with the same name replaces the bundled one
    return skills


def list_pending():
    return list(_scan(user_dir() / '_pending', 'pending').values())


def get_pending(name):
    return _scan(user_dir() / '_pending', 'pending').get(name)


def catalog_prompt():
    items = list(all_skills().values())[:40]
    if not items:
        return ''
    return ('\n\nSkills (saved instructions): when a task matches one, call use_skill(name) first and follow it exactly. After a workflow '
            'that worked well, you may propose a new skill with save_skill (the user must approve it).\n'
            + '\n'.join(f'- {s["name"]}: {s["description"][:160]}' for s in items))


def _tokens(text):
    words = (w[:-1] if len(w) > 3 and w.endswith('s') else w for w in re.findall(r'[a-z0-9]+', text.lower()))   # tests = test
    return {w for w in words if w not in STOP and len(w) > 2}


def match(query, k=2, min_score=2):
    """The skills most relevant to a request, by keyword overlap (no model call, no tokens). SKILLS=0 switches it off."""
    if os.getenv('SKILLS', '1') == '0':
        return []
    q, scored = _tokens(query), []
    for s in all_skills().values():
        score = 2 * len(q & _tokens(s['name'].replace('-', ' '))) + len(q & _tokens(s['description'] + ' ' + EXTRA_KEYWORDS.get(s['name'], '')))
        if score >= min_score:
            scored.append((score, s))
    return [s for _, s in sorted(scored, key=lambda t: -t[0])[:k]]


def save(name, description, body, pending=False):
    name = name.strip().lower()
    if not NAME.match(name):
        raise ValueError('name: lowercase letters, digits and hyphens only (max 63 characters)')
    description = ' '.join(description.split())
    if not description or len(description) > 400:
        raise ValueError('description: 1 to 400 characters')
    if not body.strip() or len(body) > MAX_BODY:
        raise ValueError(f'instructions: 1 to {MAX_BODY} characters')
    folder = user_dir() / ('_pending' if pending else '') / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: {description}\n---\n{body.strip()}\n', encoding='utf-8')
    return name


def approve(name):
    src = user_dir() / '_pending' / name
    if not NAME.match(name) or not (src / 'SKILL.md').is_file():
        raise FileNotFoundError('no such pending skill')
    dest = user_dir() / name
    shutil.rmtree(dest, ignore_errors=True)
    shutil.move(str(src), str(dest))


def delete(name, pending=False):
    if not NAME.match(name):
        raise ValueError('bad skill name')
    target = user_dir() / ('_pending' if pending else '') / name
    if not (target / 'SKILL.md').is_file():
        if not pending and name in _scan(BUNDLED, 'bundled'):
            raise ValueError('bundled skills cannot be deleted (save a skill with the same name to override it)')
        raise FileNotFoundError('no such skill')
    shutil.rmtree(target)
