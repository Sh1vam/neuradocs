---
name: fastapi-service
description: Use when asked for a FastAPI or other REST service. Layout and test conventions that pass offline.
---
1. Layout: app/__init__.py, app/main.py (app = FastAPI()), app/schemas.py (pydantic models), app/storage.py (in-memory dict or sqlite3), tests/test_api.py, conftest.py, requirements.txt, README.md.
2. Validate with pydantic and response_model. Return 201 on create and 404 when missing; 422 comes from validation.
3. Tests use fastapi.testclient.TestClient. A fixture resets the storage before every test, so tests never depend on each other.
4. No network, no background workers, no real secrets. Read settings from environment variables with safe defaults.
5. README: pip install -r requirements.txt, uvicorn app.main:app --reload, pytest.
