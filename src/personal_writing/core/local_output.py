"""Local output — save generated articles as markdown files in the project folder."""

import os
import datetime

# Project base: ~/Desktop/计算机/个人写作/
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DRAFT_DIR = os.path.join(PROJECT_DIR, "草稿")


def save_article(article_id, style, title, content, session_id=0):
    """Save an article as a local markdown file.

    File: 草稿/YYYYMMDD_HHMM_style_title.md

    Returns:
        Path to the saved file, or None if failed.
    """
    os.makedirs(DRAFT_DIR, exist_ok=True)

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M")
    safe_title = title.strip().replace("/", "／").replace(":", "：") if title else "无标题"
    # Truncate title for filename
    if len(safe_title) > 30:
        safe_title = safe_title[:30]
    filename = f"{timestamp}_{style}_{safe_title}.md"
    # Remove any remaining problematic chars
    filename = "".join(c for c in filename if c.isascii() or c in "／：-_ .")
    filepath = os.path.join(DRAFT_DIR, filename)

    # Build markdown with metadata header
    md = f"""---
id: {article_id}
style: {style}
session: {session_id}
created: {now.strftime("%Y-%m-%d %H:%M")}
status: draft
---

{content.strip()}
"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)
        return filepath
    except Exception:
        return None


def delete_article(filepath):
    """Delete a local article file."""
    try:
        if filepath and os.path.isfile(filepath):
            os.remove(filepath)
            return True
    except Exception:
        pass
    return False


def list_drafts(limit=30):
    """List draft files in the 草稿 folder."""
    if not os.path.isdir(DRAFT_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(DRAFT_DIR) if f.endswith(".md")],
        reverse=True,
    )[:limit]
    result = []
    for fname in files:
        fpath = os.path.join(DRAFT_DIR, fname)
        stat = os.stat(fpath)
        result.append({
            "filename": fname,
            "path": fpath,
            "size": stat.st_size,
            "modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return result
