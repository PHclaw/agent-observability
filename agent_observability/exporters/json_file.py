"""JSON Lines file exporter - appends each trace as a JSON line."""

from __future__ import annotations

import json
import gzip
from pathlib import Path


class JsonFileExporter:
    """
    Appends each completed trace as a JSON line to a file.

    Usage:
        exporter = JsonFileExporter("traces.jsonl")
        tracer.add_exporter(exporter)

        # Or gzip compressed:
        exporter = JsonFileExporter("traces.jsonl.gz")
    """

    def __init__(self, filepath: str | Path, compress: bool = False):
        self.filepath = Path(filepath)
        self.compress = compress

    def export(self, trace: dict):
        """Append one trace as a JSON line."""
        line = json.dumps(trace, ensure_ascii=False, default=str)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if self.compress:
            with gzip.open(self.filepath, "ab") as f:
                f.write(line.encode("utf-8") + b"\n")
        else:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    @staticmethod
    def load(filepath: str | Path, compressed: bool = False) -> list[dict]:
        """Load all traces from a JSONL file."""
        path = Path(filepath)
        traces = []
        if compressed:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        traces.append(json.loads(line))
        else:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        traces.append(json.loads(line))
        return traces
