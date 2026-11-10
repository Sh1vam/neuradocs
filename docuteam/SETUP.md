# DocuTeam setup (Windows, no GPU, Groq free tier)

## 0. Security first
- The old Groq key that was pasted into chat and into `llm_layer.py` must be treated as leaked.
  **Delete it in the Groq console and create a new one.** This project no longer contains any key.
- The key lives only in an environment variable (or a `.env` file that is git-ignored).

## 1. Install
```text
cd C:/agents/docuteam
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
pip freeze > requirements.lock
setx GROQ_API_KEY paste-your-NEW-key-here
```
Close and reopen the terminal after `setx`.

## 2. Download the local models once (needs internet)
```text
python download_models.py
```
This fills `models/` (embedder and reranker). Without it `knowledge.py` cannot start.

## 3. Check the code without any key, models or Docker
```text
python -m pytest -q tests
```
All tests should pass. They test the safety logic (path limits, command policy, kill switch,
URL guard, state file, agent loop) with a fake model.

## 4. Index and ask
```text
python cli.py ingest
python cli.py ask "How many remote days can new hires have per week?"
python cli.py feedback <request_id> approved
```
`workspace/docs/handbook.txt` is a sample document. Replace or add your own `.txt` / `.md` files, then run `ingest` again.

## 5. Kill switch
Create an empty FILE named `STOP` in the project folder to halt every loop; delete it to resume.
It must be a file, not a folder.

## 6. Coding agent (needs Docker Desktop with WSL2)
```text
docker build -t agent-sandbox:latest -f sandbox/Dockerfile sandbox
cd workspace/code
git init
git config user.name "you"
git config user.email "you@example.com"
```
Then `from coder import spec_to_tool` and call it with a specification.

## 7. Before you trust it
- Expand `golden.py` to about 25 questions from your own documents.
- Run `python run_all.py` (free, local) for a retrieval baseline; use `run_suite(llm=True)` sparingly (it spends tokens).
- Work through the launch review in Chapter 08.
