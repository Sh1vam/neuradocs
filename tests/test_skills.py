import asyncio

import pytest
from fastapi.testclient import TestClient

import main
import skillset

client = TestClient(main.app)


def test_bundled_skills_are_valid_and_match_requests():
    assert {'django-project', 'fastapi-service', 'python-cli', 'bugfix-workflow'} <= set(skillset.all_skills())
    assert skillset.match('Create a django todo app with login')[0]['name'] == 'django-project'
    assert skillset.match('fix the failing test in my calculator')[0]['name'] == 'bugfix-workflow'
    assert skillset.match('a poem about the sea') == []                      # nothing fits: nothing is injected


def test_user_skills_can_be_added_deleted_and_names_are_checked(monkeypatch, tmp_path):
    monkeypatch.setenv('SKILLS_DIR', str(tmp_path))
    skillset.save('my-style', 'Use when writing release notes for our team.', 'Always start with a one-line summary.')
    assert skillset.all_skills()['my-style']['source'] == 'user' and 'my-style' in skillset.catalog_prompt()
    skillset.delete('my-style')
    assert 'my-style' not in skillset.all_skills()
    for bad in ('../evil', 'Has Space', '', 'a' * 80):
        with pytest.raises(ValueError):
            skillset.save(bad, 'd', 'b')
    with pytest.raises(ValueError):
        skillset.delete('django-project')                                    # bundled skills are protected


def test_agent_proposed_skills_wait_for_approval(monkeypatch, tmp_path):
    monkeypatch.setenv('SKILLS_DIR', str(tmp_path))
    assert 'pending' in asyncio.run(main.tool_save_skill('release-notes', 'Use when writing release notes.', 'Summary first.')).lower()
    assert 'release-notes' not in skillset.all_skills() and 'release-notes' not in skillset.catalog_prompt()   # never used before approval
    assert [p['name'] for p in skillset.list_pending()] == ['release-notes']
    skillset.approve('release-notes')
    assert 'release-notes' in skillset.all_skills() and not skillset.list_pending()
    assert 'Summary first.' in asyncio.run(main.tool_use_skill('release-notes'))
    assert 'No such skill' in asyncio.run(main.tool_use_skill('nope'))


def test_skills_api_and_page(monkeypatch, tmp_path):
    monkeypatch.setenv('SKILLS_DIR', str(tmp_path))
    assert any(s['name'] == 'django-project' for s in client.get('/api/skills').json()['skills'])
    assert client.post('/api/skills', json={'name': 'team-style', 'description': 'Use for team replies.', 'instructions': 'Be brief.'}).status_code == 200
    assert client.post('/api/skills', json={'name': '../x', 'description': 'd', 'instructions': 'b'}).status_code == 400
    assert client.get('/api/skills/team-style').json()['body'] == 'Be brief.'
    assert client.delete('/api/skills/team-style').status_code == 200
    assert client.delete('/api/skills/django-project').status_code == 400
    assert 'Add a skill' in client.get('/skills').text


def test_third_party_skill_ships_with_its_license_and_is_found_by_ui_requests():
    folder = skillset.BUNDLED / 'frontend-design'
    assert 'Apache License' in (folder / 'LICENSE.txt').read_text(encoding='utf-8')[:500]
    assert 'frontend-design' in (skillset.BUNDLED / 'NOTICE.md').read_text(encoding='utf-8')
    assert skillset.match('Build a landing page website for a bakery')[0]['name'] == 'frontend-design'
    assert skillset.match('create a django todo app with login')[0]['name'] == 'django-project'


def test_new_skills_are_found_by_their_requests():
    assert skillset.match('create an excel budget spreadsheet')[0]['name'] == 'make-spreadsheet'
    assert skillset.match('research the best vector databases')[0]['name'] == 'research-topic'
    assert skillset.match('write a skill for our release notes')[0]['name'] == 'write-skills'


def test_the_help_skill_only_names_things_that_exist():
    import re
    root = skillset.ROOT
    body = skillset.all_skills()['neuradocs-help']['body']
    docs = '\n'.join((root / f).read_text(encoding='utf-8') for f in ('.env.example', 'README.md', 'docker-compose.yml', 'run.py'))
    missing = sorted(t for t in set(re.findall(r'\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b', body)) if t not in docs)
    assert not missing, missing                                              # every setting it names is documented
    for f in set(re.findall(r'\b[\w/]+\.py\b', body)):
        assert (root / f).exists(), f                                        # every script it names exists
    assert '/api/sandbox/status' in main.app.openapi()['paths']
