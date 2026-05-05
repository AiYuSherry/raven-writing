"""Sherry风格 — 流深 Sherry 的公众号长文风格。

基于 Sherry skill / 律海流深公众号文章：
- 温暖有说服力
- 分节论述（一/二/三/四）
- 有导语和结语
- 个人叙事+理性分析结合
"""

import os
import re

from ..core.style_engine import BaseStyle, registry


SKILL_PATHS = [
    os.path.expanduser("~/.codex/skills/sherry/SKILL.md"),
    os.path.expanduser("~/.claude/skills/Sherry/SKILL.md"),
    os.path.expanduser("~/.claude/skills/sherry/SKILL.md"),
]


def _load_skill_prompt():
    """Load the full Sherry SKILL.md as the prompt template."""
    for skill_path in SKILL_PATHS:
        if not os.path.isfile(skill_path):
            continue
        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Strip frontmatter (--- ... ---)
            content = re.sub(r'^---[\s\S]*?---\s*', '', content).strip()
            return content
        except Exception:
            continue
    return None


class SherryStyle(BaseStyle):
    name = "sherry"
    display_name = "卡兹克（公众号长文）"
    description = "卡兹克的公众号长文风格，温暖有说服力"
    _skill_prompt = None
    config = {
        "word_count": 2000,
        "sentence_length": "medium",
        "tone": "warm",
        "structure": "numbered_sections",
        "paragraph_density": "normal",
        "rhetoric_density": "medium",
        "personal_pronoun": "first_person",
        "humor_style": "dry",
        "ending_style": "summary",
    }

    def get_prompt_template(self):
        if SherryStyle._skill_prompt is None:
            SherryStyle._skill_prompt = _load_skill_prompt()
        if SherryStyle._skill_prompt:
            return SherryStyle._skill_prompt
        # Fallback to built-in prompt
        return self._builtin_prompt()

    def _builtin_prompt(self):
        return """你以"流深 Sherry"的口吻写一篇公众号长文。你的声音特征如下：

## 语言风格
- 语气温暖但有力量，像"一位有耐心的朋友在认真地帮你梳理一件事"
- 个人叙事+理性分析结合，用自己的经历引出观点
- 句子中等长度，段落完整
- 用词准确但不学术，专业但不冷僻
- 善于用具体细节说话（具体场景、具体数字、具体感受）
- 克制抒情，不煽情，让读者自己体会

## 结构特征
- 有一个吸引人的导语/开场
- 正文用一、二、三、四分节（中文大写序号）
- 每节一个小主题，节内有递进逻辑
- 结尾有升华/总结，给读者留下余味
- 全文2000字以上

## 内容范围
- AI 科普/产品体验/方法论分享/行业思考
- 从个人经历或观察切入，展开深入分析
- 既有"我"的视角，也有客观分析

## 标题风格
- 可以用"主标题：副标题"格式
- 或论断式标题（"从XX到XX"）
- 或设问式标题

## 绝对不要
- 不要用"首先/其次/最后"
- 不要用"笔者认为"
- 不要排比句堆砌
- 不要AI腔（"随着AI技术的快速发展"等）
- 不要刻意煽情

## 结尾
- 每篇文末加一行："/ 作者：流深Sherry"
"""
