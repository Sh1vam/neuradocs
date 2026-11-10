# NeuraDocs = NeuraChat + DocuTeam in one project

NeuraChat is the app (chat UI, file generation, tool-calling agent). DocuTeam sits in `docuteam/`
(unchanged) and is reached through `docs_api.py`.

Start with `CONCEPTS.md`: it follows one message through the whole system and explains each design choice.

## Run
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and paste a NEW Groq key (the old one was in source code: revoke it).
3. Put your existing `models/` and `chroma/` folders into `docuteam/`, or rebuild them:
   `python docuteam/download_models.py` then `python docuteam/cli.py ingest`
4. `python run.py` -> http://127.0.0.1:8001 (chat) and /documents (cited answers). `PORT=8010` if 8001 is busy.
5. Optional, for code execution: install Docker, then `docker build -t agent-sandbox:latest -f docuteam/sandbox/Dockerfile docuteam/sandbox`

## How the two projects are joined
- `ask_documents` is a new agent tool: the chat model can call DocuTeam (routing, rerank, citation check).
- `run_python` now runs in DocuTeam's Docker sandbox, not on your machine. Without Docker it refuses.
- `store.py` / `store_api.py`: SQLite for projects, chats, pins, messages (`/api/projects`, `/api/chats`).
- DocuTeam loads lazily on its first question, so the app starts fast. `/api/docs/status` shows what is missing.

## Fixed in NeuraChat's main.py
- Hard-coded Groq key removed (the key is read from `.env`). `setup_and_run.py` is gone for the same reason.
- `/api/mcp/*` returned 404: the static mount at "/" was registered before them. It is now last.
- CORS was `*` and the server listened on 0.0.0.0; now localhost only. `reload` is off, because files the
  code builder writes would restart the server mid-request.

## Where each concept lives
| File | Concept |
|---|---|
| main.py | FastAPI routing, Pydantic, SSE streaming, ReAct tool loop, PPT/PDF/Word generation |
| store.py, store_api.py | relational schema, foreign keys and cascade, a connection per thread |
| build_api.py | plain-text file protocol, bounded fix loop, path-traversal guard, zip packaging |
| docs_api.py | lazy loading, bridge between systems, a lock around a CPU model, sandboxed tools |
| docuteam/router.py | routing a question to the right pipeline |
| docuteam/knowledge.py | embeddings, vector database, reranking |
| docuteam/answering.py | grounded answers with citations |
| docuteam/query_cache.py | caching and cache keys |
| docuteam/limited_client.py | daily token budget |
| docuteam/sandbox.py, safe_shell.py | container isolation, command allow-list |
| docuteam/coder.py | tester and coder as separate roles, test-fix loop |
| docuteam/feedback.py, weekly.py, evals/ | feedback loop and evaluation |
| guide/ | the concept guide that came with NeuraChat |

## Sidebar and saved chats (step 2)
- Every chat is saved in `data/neurachat.db`. The sidebar shows Pinned, Projects (each with its chats) and Recent.
- Click a project to start a chat in it. Its instructions are added to the system prompt of every chat inside.
- Pin, rename and delete appear when you hover a chat. The search box looks in titles and message text.
- `/api/chat`, `/api/conversations` and `/api/mcp/chat` all read and write the same database.

## One model (openai/gpt-oss-120b)
- NeuraChat and DocuTeam both use `LLM_BIG`. `LLM_SMALL` (DocuTeam's cheap steps) falls back to it.
- Chat runs gpt-oss at low reasoning effort (`LLM_EFFORT`); Build uses medium. Reasoning counts as output tokens.
- Only image analysis needs another model (`LLM_VISION`), because gpt-oss cannot read images.
- Free Groq tier: about 8,000 tokens per minute and 200,000 per day. Build waits out per-minute limits by itself.
  Chat and Agent show a plain message instead; wait a minute and send again.

## Agent and Build modes (step 3)
- **Agent** (toggle under the input box): the model picks tools by itself: `ask_documents`, `web_search`, `run_python`,
  `generate_file`, `build_project`. The tools it used show as chips under the answer. While it works you see which tool is running; the final
  answer appears when it is ready. Hover a code block in any answer to download it as a file.
- **Agent + Build together**: the agent may first look things up (your documents, the web), must then call the builder
  once, and the reply always carries the zip link, even if the model forgets to repeat it.
- **Build**: describe a project. The model writes the files, they are tested with pytest in the Docker sandbox, failures
  go back to the model for up to 3 rounds, then you get a zip link. Without Docker you still get the zip, marked "not run".
- Attaching a document now always indexes it and switches RAG on. `.pptx` files can be read as well as `.pdf` and `.docx`.
- `/api/download` serves `.zip`. To make PDF, Word or PowerPoint files, ask in the normal chat ("make a 5-slide deck on ...").

## Where your chats are stored
- In `~/.neuradocs/neurachat.db` (on Windows: `C:\Users\<you>\.neuradocs\`), not in the project folder, so a new copy of
  the project keeps your chats. `python run.py` prints the exact path and how many chats it holds. Set `NEURACHAT_DB` to move it.
- A `data/neurachat.db` next to the code (older versions) is copied there on first start. If your old chats are in a
  different copy of the project, stop the server and copy that copy's `data/neurachat.db` to the path run.py prints.
- Chats made before the database existed were only in memory and are gone.
- `tests/ui/ui_test.js` clicks through the real page (sidebar, saved chats, projects, Build prompt). It needs Node.

## Where Build puts things, and tokens
- The project stays in `docuteam/workspace/code/builds/<name>-<id>/` (newest 10 kept) and is zipped to `outputs/`.
  Tests run in the Docker sandbox on exactly that folder, so you can open it and run it yourself.
- Open `/api/sandbox/status` to see whether the sandbox is usable and why not. The sandbox image now includes
  Django, Flask, FastAPI and pytest-django (it has no network). After pulling this update, rebuild the image once:
  `docker build -t agent-sandbox:latest -f docuteam/sandbox/Dockerfile docuteam/sandbox`. A container made from the
  old image is replaced automatically.
- Agent and Build replies show tokens in, tokens out and the estimated cost. The sidebar totals include them.
- A plain-chat message like "create a Django project" now asks whether to switch to Build mode.

## Documents page
`/documents` has an **Add document** button: pdf, docx, pptx, txt or md. The text is saved in
`docuteam/workspace/docs/` and indexed right away, so DocuTeam can answer from it with citations.

## Deploy online (it builds itself)
`python bootstrap.py` takes a fresh machine with Docker to a running app:
1. creates `.env` (asks for your Groq key, generates the web password and a sandbox token);
2. builds the images: installs the requirements (`constraints.txt` pins them to the versions of your own environment, minus
   Windows-only packages, with CPU-only torch), downloads the models, builds the sandbox service (Django, Flask, FastAPI, pytest);
3. runs the offline tests inside the built image;
4. starts everything, waits for health and checks the sandbox.
- The sandbox is its own container: no internet, read-only, non-root, memory/CPU/process limits. The app reaches it over an
  internal network with a token, so the app never needs the Docker socket. Generated code never runs in the app container.
- The site asks for a password (any username). The app refuses to listen publicly without `APP_PASSWORD`.
- HTTPS: set `DOMAIN` in `.env`, point its DNS at the server, run `docker compose --profile tls up -d`.
- Chats, index, workspace and outputs live in Docker volumes. Back them up like any database.
- **The team** (Build mode and the `build_project` tool): Researcher (GitHub search for similar projects) -> Planner (compares 3
  options, picks one, writes the spec) -> Coder -> Tester (sandbox) -> Coder fixes -> Tester. The reply carries a Team log and
  the options compared. `BUILD_TEAM=0` skips research and planning to save tokens. Agent mode also has a `search_projects` tool.

## Stress test and scaling
- `python scripts/stress_test.py --url http://127.0.0.1:8001 --readers 10 --chatters 10 --runners 4 --seconds 15` (add `--password`
  when `APP_PASSWORD` is set). Start the server with `FAKE_LLM=1` (and `FAKE_LLM_DELAY=1.0`) to load-test without spending tokens.
- Measured here with the fake model, 10 readers + 10 chat streams + 4 sandbox users: chat streams p50 1.6 s (the fake model
  takes 1 s), page reads p50 54 ms at 72 requests/s, sandbox runs 27/s, 0 errors, database intact. Before the fix the same load
  gave 10 s for everything, because one streaming chat blocked the whole server.
- What limits you online: (1) Groq: the free tier is a few requests a minute for ALL users together, so real chat traffic
  stops there long before the server does; (2) DocuTeam answers one question at a time per process (CPU model), so
  `/documents` handles roughly one question per 1-3 s; (3) one machine: SQLite is shared by the processes of one host only.
- Knobs: `WEB_CONCURRENCY=2` (more app processes, each loads the models: about 1 GB of RAM each; token totals in the sidebar
  are then per process), `SANDBOX_SLOTS=4` (parallel sandbox jobs, shares the sandbox memory limit). Scaling past one machine
  needs PostgreSQL instead of SQLite and a shared index; that is not built.

## Integrity check
`python scripts/integrity_check.py [--zip neuradocs.zip] [--db path]` checks: no keys in any file, no git metadata in
`docuteam/workspace/code`, every Python file parses, every import is in requirements.txt, every page only calls routes that
exist, Docker and compose files point at real files, every requirement is pinned, the database is intact, the zip reads back
and holds nothing that must not ship. It also runs as a test (`tests/test_integrity.py`).

## Checkpoints without a nested git repository
DocuTeam's code checkpoints (`git add`/`commit` after each step) now use a hidden repository in
`docuteam/workspace/.checkpoints.git`. `docuteam/workspace/code` has no `.git`, `.gitignore` or `.gitmodules`, so it is a plain
folder and Git or your editor never treat it as a separate repository or workspace. Ignore rules live in the hidden repository.

## Run the tests
`pip install pytest`, then `pytest tests`. They run offline with the model stubbed, and use a temporary database and
temporary folders, so your chats and documents are never touched.

## Not built yet
- The Agent shows live tool progress, but its final answer is not streamed word by word.
