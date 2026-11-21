"""Flask entry point for the NotebookLM-style MVP."""
import os

from flask import Flask, jsonify, render_template, request

from ingest import chunk_text, extract_text
from llm import (
    STUDIO_KINDS, ClaudeClient, build_chat_prompt, build_studio_prompt,
    extract_citations)
from retrieval import select_context
from store import SourceStore

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(BASE_DIR, "data", "sources.json")


def create_app(llm=None, data_path=None):
    """Build the app. Tests pass a fake llm so no API key is needed."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    store = SourceStore(data_path or DEFAULT_DATA_PATH)
    client = llm or ClaudeClient()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/sources")
    def list_sources():
        return jsonify(store.summaries())

    @app.post("/api/sources")
    def add_sources():
        if request.is_json:
            body = request.get_json(silent=True) or {}
            text = (body.get("text") or "").strip()
            if not text:
                return _error("Pasted text is empty.", 400)
            name = (body.get("name") or "").strip() or "Pasted text"
            return jsonify([store.add(name, text, chunk_text(text))]), 201
        files = request.files.getlist("files")
        if not files:
            return _error("No files were uploaded.", 400)
        added = []
        for upload in files:
            try:
                text = extract_text(upload.filename, upload.read())
            except ValueError as exc:
                return _error(str(exc), 400)
            if not text.strip():
                return _error(f"No text found in {upload.filename}.", 400)
            chunks = chunk_text(text)
            added.append(store.add(upload.filename, text, chunks))
        return jsonify(added), 201

    @app.delete("/api/sources/<source_id>")
    def delete_source(source_id):
        if not store.remove(source_id):
            return _error("Source not found.", 404)
        return "", 204

    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True) or {}
        question = (body.get("question") or "").strip()
        if not question:
            return _error("Ask a question first.", 400)
        chunks = store.chunks_for(body.get("source_ids"))
        if not chunks:
            return _error("Add or select at least one source.", 400)
        context = select_context(chunks, question)
        system, user = build_chat_prompt(question, context)
        return _answer(client, system, user, context)

    @app.post("/api/studio")
    def studio():
        body = request.get_json(silent=True) or {}
        kind = body.get("kind")
        if kind not in STUDIO_KINDS:
            return _error("Unknown Studio output.", 400)
        chunks = store.chunks_for(body.get("source_ids"))
        if not chunks:
            return _error("Add or select at least one source.", 400)
        context = select_context(chunks, None)
        system, user = build_studio_prompt(kind, context)
        title = STUDIO_KINDS[kind]["title"]
        return _answer(client, system, user, context, title)

    return app


def _answer(client, system, user, context, title=None):
    """Call Claude and attach the passages behind each citation."""
    try:
        text = client.complete(system, user)
    except Exception as exc:  # show API/key errors in the UI
        return _error(f"Claude request failed: {exc}", 502)
    citations = [
        {
            "n": n,
            "source": context[n - 1]["source_name"],
            "text": context[n - 1]["text"],
        }
        for n in extract_citations(text, len(context))]
    return jsonify({"title": title, "answer": text, "citations": citations})


def _error(message, status):
    return jsonify({"error": message}), status


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
