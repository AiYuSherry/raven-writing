"""郑戈论文风格 — 内置学术作者写作模型。"""

import os
import re

from ..core.style_engine import BaseStyle


SKILL_ROOT = os.path.expanduser("~/.codex/skills/zheng-ge-academic-author")
SKILL_PATH = os.path.join(SKILL_ROOT, "SKILL.md")
SUPPLEMENT_FILES = [
    "references/research/problem-consciousness.md",
    "references/research/concept-lexicon.md",
    "references/research/argument-patterns.md",
    "references/research/paper-structure-patterns.md",
    "references/research/expression-dna.md",
    "references/examples/topic-outline-sample.md",
    "references/examples/rewrite-sample.md",
]


def _read_text(path, limit=None):
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return ""
    text = re.sub(r"^---[\s\S]*?---\s*", "", text).strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip() + "\n\n[以下内容已截断，完整材料见本地 skill references。]"
    return text


def _load_prompt():
    """Load the local Zheng Ge author model plus compact evidence snippets."""
    main = _read_text(SKILL_PATH, limit=30000)
    if not main:
        main = """# 郑戈论文风格

基于郑戈法学论文写作模型生成论文型文本。必须保持学术边界，不冒充作者本人，不编造文献、法条、案例、页码或新近态度。"""

    supplements = []
    for rel in SUPPLEMENT_FILES:
        text = _read_text(os.path.join(SKILL_ROOT, rel), limit=2200)
        if text:
            supplements.append(f"## {rel}\n{text}")

    supplement_text = "\n\n".join(supplements)
    return f"""{main}

## 项目内置补充材料摘要
以下摘录仅用于增强论文结构、概念和表达约束；事实、规范和文献仍以用户材料或写作前研究为准。

{supplement_text}
"""


class ZhengGeAcademicStyle(BaseStyle):
    name = "zheng_ge_academic"
    display_name = "郑戈论文风格"
    description = "郑戈学术作者写作模型，适合生成法学选题、摘要、引言、提纲和章节论证"
    _skill_prompt = None
    config = {
        "word_count": 5000,
        "sentence_length": "long",
        "tone": "academic",
        "structure": "academic_paper",
        "paragraph_density": "dense",
        "rhetoric_density": "low",
        "personal_pronoun": "none",
        "humor_style": "none",
        "ending_style": "theoretical_summary",
        "category": "academic",
    }

    def get_prompt_template(self):
        if ZhengGeAcademicStyle._skill_prompt is None:
            ZhengGeAcademicStyle._skill_prompt = _load_prompt()
        return ZhengGeAcademicStyle._skill_prompt

    def post_process(self, content):
        return content.strip()
