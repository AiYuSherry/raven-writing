"""Convert Markdown-ish writing drafts to clean plain text."""

import re


def markdown_to_txt(markdown):
    """Convert Markdown to a copy-friendly txt format.

    The converter is intentionally conservative: it removes Markdown syntax
    while preserving content order, command lines, numbered steps, and spacing.
    """
    text = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    out = []
    in_fence = False
    table_block = []

    def flush_table():
        nonlocal table_block
        if table_block:
            out.extend(_table_to_plain(table_block))
            table_block = []

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_table()
            in_fence = not in_fence
            continue

        if in_fence:
            out.append(line.strip())
            continue

        if _is_table_line(stripped):
            table_block.append(stripped)
            continue
        flush_table()

        line = _clean_markdown_line(line)
        out.append(line)

    flush_table()
    return _normalize_blank_lines(out)


def _clean_markdown_line(line):
    line = line.strip()
    if not line:
        return ""

    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^>\s*", "", line)
    line = re.sub(r"^\s*[-*+]\s+", "", line)
    line = re.sub(r"^(\d+)\.\s+", r"\1. ", line)
    line = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", line)
    line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    line = re.sub(r"`([^`]+)`", r"\1", line)
    line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
    line = re.sub(r"__([^_]+)__", r"\1", line)
    line = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", line)
    line = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", line)
    return line.strip()


def _is_table_line(line):
    return line.startswith("|") and line.endswith("|") and "|" in line[1:-1]


def _split_table_row(line):
    return [_clean_markdown_line(cell.strip()) for cell in line.strip("|").split("|")]


def _is_separator_row(cells):
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def _table_to_plain(lines):
    rows = [_split_table_row(line) for line in lines]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    if len(rows) >= 2 and _is_separator_row(rows[1]):
        headers = rows[0]
        body = rows[2:]
    else:
        headers = []
        body = rows

    plain = []
    for row in body:
        if not any(row):
            continue
        if headers and len(headers) == len(row):
            for header, cell in zip(headers, row):
                if header or cell:
                    plain.append(f"{header}：{cell}".strip("："))
            plain.append("")
        else:
            plain.append(" / ".join(cell for cell in row if cell))
    return plain


def _normalize_blank_lines(lines):
    cleaned = []
    blank = 0
    for line in lines:
        line = line.rstrip()
        if not line:
            blank += 1
            if blank <= 1:
                cleaned.append("")
            continue
        blank = 0
        cleaned.append(line)
    return "\n".join(cleaned).strip() + "\n"
