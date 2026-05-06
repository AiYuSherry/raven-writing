"""Local file storage for material-library uploads."""

import hashlib
import os
import re
import uuid

from ..db import schema


def base_dir():
    return os.path.join(schema.DB_DIR, "material_library")


def files_dir():
    return os.path.join(base_dir(), "files")


def safe_filename(name, fallback="material.txt"):
    """Return a filesystem-safe filename while preserving readable CJK names."""
    base = os.path.basename(name or fallback)
    base = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", base).strip("._")
    if not base:
        base = fallback
    return base[:180]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_bytes(library_id, filename, data, document_id=None):
    """Save uploaded bytes under data/material_library/files and return metadata."""
    root = files_dir()
    os.makedirs(root, exist_ok=True)
    digest = sha256_bytes(data)
    safe = safe_filename(filename)
    doc_segment = str(document_id or uuid.uuid4().hex[:12])
    target_dir = os.path.join(root, str(int(library_id)), doc_segment)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, safe)
    with open(target, "wb") as f:
        f.write(data)
    return {"path": target, "filename": safe, "sha256": digest, "size": len(data)}


def save_text(library_id, title, text, document_id=None):
    data = (text or "").encode("utf-8")
    filename = safe_filename(title or "pasted-material.txt")
    if "." not in filename:
        filename += ".txt"
    return save_bytes(library_id, filename, data, document_id=document_id)
