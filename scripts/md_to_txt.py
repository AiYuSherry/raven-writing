#!/usr/bin/env python3
"""Convert a Markdown file or stdin to clean txt."""

import argparse
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from personal_writing.utils.md_to_txt import markdown_to_txt  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Convert Markdown-ish text to plain txt.")
    parser.add_argument("input", nargs="?", help="Markdown file path. Omit to read stdin.")
    parser.add_argument("-o", "--output", help="Output txt path. Omit to print stdout.")
    args = parser.parse_args()

    if args.input:
        with open(os.path.expanduser(args.input), "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    else:
        source = sys.stdin.read()

    result = markdown_to_txt(source)
    if args.output:
        with open(os.path.expanduser(args.output), "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    main()
