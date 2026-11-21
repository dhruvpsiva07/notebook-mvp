"""JSON-file storage for sources and their chunks."""
import json
import os
import threading
import uuid


class SourceStore:
    """Keeps sources in memory and mirrors them to a JSON file."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._sources = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                for source in json.load(handle):
                    self._sources[source["id"]] = source

    def add(self, name, text, chunks):
        """Save a new source and return its summary."""
        source = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "chars": len(text),
            "chunks": chunks,
        }
        with self._lock:
            self._sources[source["id"]] = source
            self._save()
        return _summary(source)

    def remove(self, source_id):
        """Delete a source. Returns False if it did not exist."""
        with self._lock:
            if self._sources.pop(source_id, None) is None:
                return False
            self._save()
        return True

    def summaries(self):
        """List sources without their chunk text."""
        with self._lock:
            return [_summary(s) for s in self._sources.values()]

    def chunks_for(self, source_ids=None):
        """Chunks of the given sources, or of all sources if ids is None."""
        with self._lock:
            selected = [
                s for s in self._sources.values()
                if source_ids is None or s["id"] in source_ids]
            return [
                {"source_id": s["id"], "source_name": s["name"], "text": text}
                for s in selected for text in s["chunks"]]

    def _save(self):
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        temp_path = self.path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(list(self._sources.values()), handle)
        os.replace(temp_path, self.path)


def _summary(source):
    return {
        "id": source["id"],
        "name": source["name"],
        "chars": source["chars"],
        "chunks": len(source["chunks"]),
    }
