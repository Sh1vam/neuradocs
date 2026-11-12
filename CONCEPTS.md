# Follow one message through NeuraDocs

Read this next to the code. Each step names the file, then the idea it teaches.

## 1. Plain chat (the default mode)
1. **Browser** (`static/index.html`, `send()`): builds one JSON request: message, chat id, project id, model, stream flag.
2. **Validation** (`main.py`, `ChatRequest`): Pydantic checks the JSON before your code runs. Bad input never reaches the model.
3. **Memory** (`store.py`): the model remembers nothing between calls. "Memory" is the history you send again each time,
   so the server loads the last 20 messages from SQLite. Only the last N are sent because the context window is limited and
   every token costs money and time.
4. **System prompt**: the base prompt plus the project's instructions. That is the whole "projects" feature.
5. **One gate for model calls** (`llm_client.py`): every call passes through `GroqAdapter`. gpt-oss reasons before it
   answers, and that reasoning is billed as output tokens, so chat asks for low effort and Build for medium.
6. **Streaming** (`token_stream` in `main.py`): the reply travels as server-sent events, one `data: {...}` line per piece,
   so words appear at once instead of after the whole answer. The finished reply is saved to the database. If the
   stream breaks or you press stop, the partial reply is saved anyway (`finally`).
7. **Sidebar**: `refreshSidebar()` re-reads the database. The page keeps no copy of your chats, so there is nothing to drift.

Token counting for Agent and Build uses the same gate: `new_usage()` starts a per-request counter (a context variable), and
every model call made while serving that request adds to it, including calls inside tools and worker threads.

## 2. Documents with citations (`/documents`, DocuTeam)
1. **Routing** (`router.py`): is this a documents question, small talk, or a code request? Similarity to example sentences
   decides first, and a small model is only asked when that is unclear. Cheap checks first, expensive ones last.
2. **Retrieval** (`knowledge.py`): turn the question into a vector, find the 15 nearest passages (fast, approximate),
   then let a cross-encoder reread each one together with the question and keep the best 4 (slow, precise).
   Two stages: one for recall, one for precision.
3. **Grounded answer** (`answering.py`): the model may only use those passages and must cite them as [1], [2].
   The code then checks that every cited number exists. That is the green or amber line under an answer.
4. **Cache** (`query_cache.py`): a repeated question returns the stored answer. Only grounded answers are stored, and the
   key includes the release version, so a new index cannot serve stale answers.
5. **Budget and retries** (`limited_client.py`, `retry.py`): a daily token budget, and waiting out per-minute limits.
6. **Feedback**: Helpful or Not helpful goes to `feedback.jsonl`, which the weekly review reads.
7. **Add document** (`docs_api.py`): extract text, save it, then index only that file: split into chunks, embed, store.

## 3. Agent mode (tools)
`run_mcp_agent` in `main.py` is a loop: the model sees a list of tools, may ask for one, the server runs it and sends the
result back, and this repeats (at most 5 rounds) until the model answers in plain text. Tools are plain functions
registered with `@mcp_tool`. Three are the bridge between the two projects:
- `ask_documents`: DocuTeam as one tool among others (composition).
- `run_python`: runs in Docker with no network, so a prompt hidden in a PDF cannot delete your files.
- `build_project`: the same builder the Build button uses.

With Build also on, the page sends `build: true`; the server adds a rule to the system prompt ("call build_project once") and
`keep_download_links` re-adds the zip link if the model leaves it out. Models paraphrase tool output, so anything the user
must see should be attached by code, not trusted to the model.

While an agent works, the page shows which tool is running. The agent runs in its own thread and puts progress events
in a queue; the server turns the queue into server-sent events. If every round is spent on tools, the loop asks once
more, without tools, for the answer (otherwise the page would show an empty reply).

## 4. Build mode (`build_api.py`)
1. The model returns files as plain-text blocks, not JSON: code inside JSON needs escaping and models get it wrong.
2. Every path is checked, so `../evil.py` cannot escape the build folder.
3. pytest runs in the sandbox. A `conftest.py` in the project root is what lets `tests/` import the code next to it.
4. If tests fail, the output and the current files go back to the model. The loop stops after 3 rounds; an endless
   "retry until green" loop only burns tokens.
5. A rate limit in round 2 or 3 keeps the files from round 1. Rate limits in any round are waited out, not fatal.
6. The result is zipped with `zipfile`. RAR is a closed format that Python cannot write, and zip opens everywhere.

## 5. Skills (muscle memory)
A skill (`skills/<name>/SKILL.md`, code in `skillset.py`) is saved instructions plus a short description of when to use them.
- **Progressive disclosure**: the prompt carries only names and descriptions; `use_skill` loads the full text on demand.
- **Deterministic reuse**: Build picks matching skills by keyword overlap (no model call), so the Coder gets the same
  conventions every time instead of re-inventing them.
- **A skill is a prompt that persists.** If an agent could save skills freely, one poisoned web page could steer every later
  task. So the agent may only *propose* (`save_skill` writes to `_pending`); you approve on the Skills page.

## 6. Safety checklist (what each change protects)
- Key only in `.env` (it was once in source code). Server on 127.0.0.1 only; CORS limited to this app.
- Generated code only in Docker. Uploads capped at 20 MB. Generated file names sanitised.
- Routes registered before the static mount: a mount at `/` swallows every path after it.

## Experiments
- Set `LLM_EFFORT=high` in `.env` and compare answer quality, speed and the token counter.
- Add a project instruction ("answer in two sentences") and watch the system prompt change in the tests.
- Ask the same question twice on `/documents`: the second answer comes from the cache, without passages.
- Run `pytest tests -q`, then break something (remove the `finally` in `token_stream`) and see which test fails.
