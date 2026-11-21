# Notebook MVP

A NotebookLM-style web app in Flask. You upload sources, and Claude answers
only from them. Every claim gets a clickable citation that shows the exact
passage it came from.

## What maps to which NotebookLM layer

| Layer | File | What it does |
|---|---|---|
| 1. Ingestion | `ingest.py` | Parses PDF/TXT/MD and splits text into ~1,200-char chunks with 200-char overlap |
| 2. Retrieval | `retrieval.py` | Small notebooks (under ~60k chars) are sent whole; larger ones use BM25 keyword search |
| 3. Grounding | `llm.py` | Numbers chunks `[S1]...[Sn]`, tells Claude to use and cite only those, and drops invalid citations |
| 4. Model | `llm.py` | Claude via the Anthropic SDK (`CLAUDE_MODEL` env var to change it) |
| 5. Studio | `llm.py` + `/api/studio` | Study guide, FAQ, briefing doc: fixed prompts over the same context |
| Storage | `store.py` | Sources saved to `data/sources.json` |

## Run it

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # Windows: set ANTHROPIC_API_KEY=...
python app.py
```

Then open http://localhost:5000.

## Test and lint

```bash
pytest -q      # offline: uses a fake LLM, no API key needed
flake8
```

## Next steps

1. **Embeddings:** swap BM25 for vector search (e.g. Voyage embeddings and
   numpy cosine similarity) so "car" matches "vehicle".
2. **Streaming:** use `client.messages.stream` and server-sent events so
   answers appear as they are written.
3. **Chat memory:** send the last few turns along with the question.
4. **More Studio outputs:** mind map (ask for JSON and render it with a graph
   library) or audio overview (a two-host script plus text-to-speech).
5. **Notebooks:** add a `notebook_id` to sources so you can keep separate
   subjects, e.g. one per class.
