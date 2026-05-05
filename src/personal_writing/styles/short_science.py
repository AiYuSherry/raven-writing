"""短科普风格 — 客观亲切的短科普，一篇讲清楚一个东西。

基于用户的灵感收集器/归档skill等工具介绍文章：
- 痛点开场 → 我的方案 → 怎么用 → 效果/价值
- 短而清晰，不啰嗦
- 客观亲切，不端架子
"""

from ..core.style_engine import BaseStyle, registry


class ShortScienceStyle(BaseStyle):
    name = "short_science"
    display_name = "短科普"
    description = "客观亲切的短科普，一篇讲清楚一个东西"
    config = {
        "word_count": 500,
        "sentence_length": "short_to_medium",
        "tone": "objective",
        "structure": "pain_point_to_solution",
        "paragraph_density": "normal",
        "rhetoric_density": "low",
        "personal_pronoun": "mixed",
        "humor_style": "none",
        "ending_style": "summary",
    }

    def get_prompt_template(self):
        return """你写一篇简短的科普/介绍文章。你的声音特征如下：

## 语言风格
- 客观但亲切，像是给朋友介绍一个好用的东西
- 句子短到中等长度，段落紧凑
- 用具体例子说明，不空谈概念
- 直接、清晰、不啰嗦

## 结构特征（建议但不强制）
可以用小标题分隔内容，但小标题格式为「小标题：内容」——即小标题后跟冒号，然后直接接正文，不要单独占一行作为标题。

1. 痛点开场：描述一个很多人都有但没解决的困扰
2. 引出方案：所以我做了/用了什么
3. 怎么用：简单说明用法（附具体例子）
4. 效果/价值：解决了什么问题，带来了什么改变
5. 收尾：一句话总结或进一步信息

## 字数控制
- 全文500字左右
- 每个部分简洁有力，不展开太多

## 绝对不要
- 不要用"首先/其次/最后"
- 不要用"随着...的发展"
- 不要用"众所周知"
- 不要过度解释背景
- 不要AI腔
"""
