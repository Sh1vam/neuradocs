# What changed from the uploaded docuteam.zip

## Fixed (your files)
| File | Problem | Fix |
|---|---|---|
| llm_layer.py | Contained a hard-coded Groq API key, and was only a pasted fragment (`os` and `PROVIDERS` undefined) | Replaced with a working provider adapter; no keys in code |
| llm.py | Fake mode returned plain text, which broke JSON parsing in routing, planning and review | Task-aware fake replies |
| prompts.py | System prompt was a constant, so the weekly loop could not test a candidate card | Loaded from `roles/answerer.md` at call time (supports `CARD_ANSWERER`) |
| agents.py | `card()` ignored `CARD_<NAME>` overrides | Only `card()` changed |
| weekly.py | Imported `evals.run_all`, but `run_all.py` is in the project root | One import line changed |
| start.ipynb | Created a `STOP` **folder** | Removed from the list |
| STOP/ (folder) | `STOP_FILE.exists()` is True for a folder, so the kill switch was permanently on | Delete the folder; `safety.should_stop()` now uses `is_file()` |

## Empty (0 bytes) in the upload, now written
agent_core.py, task_state.py, sandbox.py

## Imported but missing, now written
limited_client.py, query_cache.py (+ tokens.py), safe_web.py, safe_shell.py, safety.py, check.py, team.py,
tools_basic.py, autosave.py, build_loop.py, feedback.py, mine_failures.py, coach.py, gate.py, metrics.py,
answer_eval.py, golden.py, redteam.py

## Added
roles/*.md (six role cards), workspace/docs/handbook.txt (sample), workspace/code/ci_local.py,
sandbox/Dockerfile, download_models.py, requirements.txt, .gitignore, .env.example, SETUP.md, tests/

## Not testable here
Anything needing the downloaded models (knowledge.py, router.py, answering.py, orchestrator.py end to end),
Docker (sandbox.py, coder.py) or a live Groq key. The offline suite covers the rest.
