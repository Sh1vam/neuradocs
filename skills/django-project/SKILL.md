---
name: django-project
description: Use when asked to create a Django project, website or REST app. Layout, settings and pytest-django setup that run offline in the sandbox.
---
Follow this workflow every time.
1. Layout: manage.py, config/ (__init__.py, settings.py, urls.py, wsgi.py), one app such as core/ (__init__.py, models.py, views.py, urls.py, admin.py, migrations/__init__.py), tests/, pytest.ini, requirements.txt, README.md. Add templates/ only when HTML pages are requested.
2. settings.py: SQLite database (BASE_DIR / "db.sqlite3"), SECRET_KEY from the environment with a development default, DEBUG from the environment, only the apps you use, no third-party packages.
3. pytest.ini must contain: [pytest], DJANGO_SETTINGS_MODULE = config.settings, pythonpath = ., python_files = test_*.py.
4. Tests use pytest-django: @pytest.mark.django_db and the client fixture. One test per view and one per model rule (validation, ordering, __str__). No network access.
5. Views stay small. APIs return JsonResponse, validate input, use get_object_or_404 and proper status codes (201, 400, 404).
6. requirements.txt lists Django with a version range. README gives: python manage.py migrate, python manage.py runserver, pytest.
7. Before finishing, check that every import resolves and every url name used in the tests exists.
