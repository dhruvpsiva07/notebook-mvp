"""Layer 1: turn uploaded files into clean text and overlapping chunks."""
import io
import re

from pypdf import PdfReader

SUPPORTED_TYPES = (".txt", ".md", ".pdf")


def extract_text(filename, data):
    """Return the plain text of an uploaded file's bytes."""
    ext = _extension(filename)
    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")
    supported = ", ".join(SUPPORTED_TYPES)
    raise ValueError(f"Unsupported file type '{ext}'. Use {supported}.")


def chunk_text(text, max_chars=1200, overlap=200):
    """Split text into chunks along paragraph boundaries.

    Each new chunk starts with the last `overlap` characters of the
    previous one so an idea that spans a boundary is not lost.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        for piece in _split_long(paragraph, max_chars):
            if current and len(current) + len(piece) + 2 > max_chars:
                chunks.append(current)
                tail = current[-overlap:] if overlap else ""
                current = f"{tail}\n\n{piece}" if tail else piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def _split_long(paragraph, max_chars):
    """Break a paragraph longer than max_chars into sentence groups."""
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces = []
    buffer = ""
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
        while len(sentence) > max_chars:
            if buffer:
                pieces.append(buffer)
                buffer = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if not sentence:
            continue
        if buffer and len(buffer) + len(sentence) + 1 > max_chars:
            pieces.append(buffer)
            buffer = sentence
        else:
            buffer = f"{buffer} {sentence}" if buffer else sentence
    if buffer:
        pieces.append(buffer)
    return pieces


def _extension(filename):
    dot = (filename or "").rfind(".")
    return filename[dot:].lower() if dot != -1 else ""
