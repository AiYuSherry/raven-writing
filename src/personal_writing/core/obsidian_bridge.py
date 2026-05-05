"""Obsidian Vault bridge — read from and write to Obsidian."""

import os
import datetime


# Obsidian vault base path
VAULT_PATH = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"
)
WORKS_FOLDER = os.path.join(VAULT_PATH, "我的作品")


def archive_to_works(content, title, source_style=""):
    """Archive an article to Obsidian Vault's 我的作品 folder.

    File format: YYYYMMDD - 标题.md

    Args:
        content: Article content (markdown)
        title: Article title
        source_style: Original style name (for metadata)

    Returns:
        Path to the saved file, or None if vault doesn't exist.
    """
    if not os.path.isdir(VAULT_PATH):
        raise FileNotFoundError(f"Obsidian vault not found at: {VAULT_PATH}")

    os.makedirs(WORKS_FOLDER, exist_ok=True)

    today = datetime.date.today().strftime("%Y%m%d")
    safe_title = title.strip().replace("/", "／").replace(":", "：") if title else "无标题"
    filename = f"{today} - {safe_title}.md"
    filepath = os.path.join(WORKS_FOLDER, filename)

    # Build markdown content with optional metadata
    md = content.strip()
    if not md.startswith("#"):
        md = f"# {title}\n\n{md}" if title else md

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)

    return filepath


def list_works(limit=20):
    """List recent articles from 我的作品 folder."""
    if not os.path.isdir(WORKS_FOLDER):
        return []
    files = sorted(
        [f for f in os.listdir(WORKS_FOLDER) if f.endswith(".md")],
        reverse=True,
    )[:limit]
    return files


def read_work(filename):
    """Read an article from 我的作品 folder by filename."""
    filepath = os.path.join(WORKS_FOLDER, filename)
    if not os.path.isfile(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()
