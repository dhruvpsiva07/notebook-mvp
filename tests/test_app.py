"""Offline tests: a fake LLM stands in for Claude, so no API key needed."""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from ingest import chunk_text, extract_text  # noqa: E402
from llm import extract_citations, format_context  # noqa: E402
from retrieval import BM25Index, select_context  # noqa: E402


class FakeLLM:
    """Records prompts and replies with a fixed cited answer."""

    def __init__(self, reply="Mitochondria make ATP [S1]. Unknown [S99]."):
        self.reply = reply
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.reply


@pytest.fixture
def fake():
    return FakeLLM()


@pytest.fixture
def client(tmp_path, fake):
    app = create_app(llm=fake, data_path=str(tmp_path / "sources.json"))
    app.testing = True
    return app.test_client()


def test_chunks_respect_size_and_overlap():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(20))
    chunks = chunk_text(text, max_chars=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    assert chunks[1].startswith(chunks[0][-50:])


def test_long_sentence_is_split():
    chunks = chunk_text("x" * 3000, max_chars=1000, overlap=0)
    assert [len(c) for c in chunks] == [1000, 1000, 1000]


def test_extract_text_rejects_unknown_type():
    with pytest.raises(ValueError):
        extract_text("photo.png", b"data")


def test_bm25_ranks_relevant_chunk_first():
    chunks = [
        {"text": "The French revolution began in 1789."},
        {"text": "Photosynthesis converts light into chemical energy."},
        {"text": "Plants use chlorophyll for photosynthesis in leaves."},
    ]
    hits = BM25Index(chunks).search("how does photosynthesis work", k=2)
    assert len(hits) == 2
    assert all("hotosynthesis" in h["text"] for h in hits)


def test_select_context_sends_small_notebooks_whole():
    chunks = [{"text": "short"}, {"text": "also short"}]
    assert select_context(chunks, "anything") == chunks


def test_select_context_spreads_large_notebooks_for_studio():
    chunks = [{"text": "a" * 1000} for _ in range(100)]
    picked = select_context(chunks, None, budget=10_000)
    assert len(picked) == 10


def test_citations_ignore_numbers_out_of_range():
    assert extract_citations("A [S2] b [S1][S2] c [S9]", 3) == [1, 2]


def test_format_context_numbers_chunks():
    text = format_context([{"source_name": "a.txt", "text": "hello"}])
    assert text == "[S1] (from a.txt)\nhello"


def test_paste_upload_list_and_delete(client):
    res = client.post("/api/sources", json={"name": "Bio", "text": "Cells."})
    assert res.status_code == 201
    source_id = res.get_json()[0]["id"]
    assert client.get("/api/sources").get_json()[0]["name"] == "Bio"
    assert client.delete(f"/api/sources/{source_id}").status_code == 204
    assert client.get("/api/sources").get_json() == []
    assert client.delete(f"/api/sources/{source_id}").status_code == 404


def test_file_upload(client):
    data = {"files": (io.BytesIO(b"Notes about cells."), "notes.md")}
    res = client.post(
        "/api/sources", data=data, content_type="multipart/form-data")
    assert res.status_code == 201
    assert res.get_json()[0]["name"] == "notes.md"


def test_bad_file_type_is_rejected(client):
    data = {"files": (io.BytesIO(b"x"), "pic.png")}
    res = client.post(
        "/api/sources", data=data, content_type="multipart/form-data")
    assert res.status_code == 400


def test_chat_is_grounded_and_cited(client, fake):
    client.post("/api/sources", json={
        "name": "Bio", "text": "Mitochondria produce ATP for the cell."})
    res = client.post("/api/chat", json={"question": "What makes ATP?"})
    body = res.get_json()
    assert res.status_code == 200
    assert [c["n"] for c in body["citations"]] == [1]
    assert body["citations"][0]["source"] == "Bio"
    system, user = fake.calls[0]
    assert "ONLY" in system
    assert "Mitochondria produce ATP" in user


def test_chat_respects_selected_sources(client, fake):
    first = client.post("/api/sources", json={"name": "A", "text": "Alpha."})
    client.post("/api/sources", json={"name": "B", "text": "Beta."})
    first_id = first.get_json()[0]["id"]
    client.post("/api/chat", json={"question": "q", "source_ids": [first_id]})
    user = fake.calls[0][1]
    assert "Alpha." in user
    assert "Beta." not in user


def test_chat_requires_sources_and_question(client):
    assert client.post("/api/chat", json={"question": "hi"}).status_code == 400
    client.post("/api/sources", json={"text": "x"})
    assert client.post("/api/chat", json={"question": " "}).status_code == 400


def test_studio_outputs(client):
    client.post("/api/sources", json={"text": "Some content."})
    res = client.post("/api/studio", json={"kind": "faq"})
    assert res.status_code == 200
    assert res.get_json()["title"] == "FAQ"
    assert client.post(
        "/api/studio", json={"kind": "podcast"}).status_code == 400


def test_llm_failure_returns_502(tmp_path):
    class Broken:
        def complete(self, system, user):
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    app = create_app(llm=Broken(), data_path=str(tmp_path / "s.json"))
    test_client = app.test_client()
    test_client.post("/api/sources", json={"text": "x"})
    res = test_client.post("/api/chat", json={"question": "q"})
    assert res.status_code == 502
    assert "ANTHROPIC_API_KEY" in res.get_json()["error"]


def test_sources_persist_across_restarts(tmp_path, fake):
    path = str(tmp_path / "sources.json")
    create_app(llm=fake, data_path=path).test_client().post(
        "/api/sources", json={"name": "Kept", "text": "Persisted."})
    reloaded = create_app(llm=fake, data_path=path).test_client()
    assert reloaded.get("/api/sources").get_json()[0]["name"] == "Kept"


def test_index_page_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Studio" in res.data
