---
name: neuradocs-help
description: Use when the user asks how NeuraDocs itself works or is set up: modes, pages, settings and environment variables, sandbox and internet access, skills, deployment, troubleshooting.
---
Answer from this page. If something is not listed here, say you do not know instead of guessing.

Modes (under the input box)
- Plain chat: answers only. It cannot run code or write files, except PowerPoint, PDF and Word files made by name ("make a 5-slide deck on X").
- Agent: the model uses tools: ask_documents, rag_search, web_search, search_projects, run_python, generate_file (pptx, pdf, docx, xlsx, notebook, chart), build_project, use_skill, save_skill. Progress shows while it works.
- Build: describe a project. Research (GitHub), planning (3 options), coding, tests in the sandbox, up to 3 fix rounds, then a zip. The project stays in docuteam/workspace/code/builds/.
- Agent and Build together: the agent may look things up first, then must call build_project once.
Pages: / (chat), /documents (cited answers from your documents, with an Add document button), /skills, /docs (the API).

Where things are
- Chats and projects: ~/.neuradocs/neurachat.db (Docker: the data volume). python run.py prints the path and the counts.
- Your skills: a skills folder next to that database. Bundled skills: skills/ in the project.
- Files the app makes: outputs/. Builds: docuteam/workspace/code/builds/ (the newest 10).

Settings (.env)
- GROQ_API_KEY is required. LLM_BIG is the model (openai/gpt-oss-120b). LLM_SMALL defaults to LLM_BIG. LLM_VISION is for image analysis only. LLM_EFFORT sets the reasoning effort of chat (low, medium, high).
- APP_PASSWORD is the login password of the web page (the browser asks for a username: anything, and this password). It is required whenever HOST is not 127.0.0.1, which is always the case in Docker. SANDBOX_TOKEN is a shared secret between the app and the sandbox service: you invent it, nobody issues it. python scripts/setup_env.py adds missing settings and generates both. DOMAIN turns on HTTPS (docker compose --profile tls up -d).
- The app listens on port 8001. APP_PORT is the port on your machine; APP_BIND says which address (127.0.0.1 by default). After editing .env run docker compose up -d.
- BUILD_TEAM=0 skips research and planning. SKILLS=0 stops automatic skills in Build. SKILL_CHARS caps what one skill adds to a prompt. SKILLS_DIR moves your skills.
- WEB_CONCURRENCY sets the number of app processes, SANDBOX_SLOTS the parallel sandbox jobs, NEURACHAT_DB the database path, GITHUB_TOKEN raises the GitHub search limit, FAKE_LLM=1 runs load tests without spending tokens.

Sandbox and internet
- Generated code runs only in the sandbox (Docker). By default it has no internet.
- To allow it: in .env set SANDBOX_PROXY=http://egress:3128 (and SANDBOX_INSTALL=1 so the tester runs pip install on requirements.txt), then run docker compose --profile internet up -d. Only the domains in EGRESS_ALLOW are reachable (PyPI, GitHub and npm by default). docker compose logs egress shows every allowed and denied connection.
- Local Docker mode: SANDBOX_NETWORK=bridge gives full internet and LAN access. Not recommended.
- /api/sandbox/status says whether the sandbox works and why not.

Running and deploying
- Local: python run.py (it prints a preflight table first). Online: python bootstrap.py (builds the images, downloads the models, runs the tests, starts everything).
- Tests: pytest tests. Stress test: python scripts/stress_test.py. Integrity check: python scripts/integrity_check.py.

Troubleshooting
- Rate limit message: the free Groq tier allows about 8,000 tokens per minute. Wait a minute. Build waits by itself.
- "Tests were NOT run": open /api/sandbox/status. Usually Docker is not running or the image is missing: docker build -t agent-sandbox:latest -f docuteam/sandbox/Dockerfile docuteam/sandbox.
- Previous chats missing: check the database path that run.py prints.
- Scanned PDF: there is no OCR, and the app says so.
