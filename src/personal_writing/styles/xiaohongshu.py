"""小红书风格 — emoji点缀的短笔记，钩子开头+标签结尾。

基于用户的小红书笔记：
- emoji作为段落标记
- 开头钩子吸引点击
- 短段、快节奏、可扫描
- 技术拆解（可选）
- 末尾话题标签
"""

from ..core.style_engine import BaseStyle, registry


class XiaohongshuStyle(BaseStyle):
    name = "xiaohongshu"
    display_name = "小红书"
    description = "emoji点缀的短笔记，钩子开头+标签结尾"
    config = {
        "word_count": 600,
        "sentence_length": "very_short",
        "tone": "casual",
        "structure": "hook_to_content",
        "paragraph_density": "tight",
        "rhetoric_density": "low",
        "personal_pronoun": "first_person",
        "humor_style": "dry",
        "ending_style": "open_ended",
    }

    def get_prompt_template(self):
        return """你写一篇小红书笔记。你的风格特征如下：

## 语言风格
- 非常简短，一段1-2句
- 用emoji点缀段落（🚀🔧✨🎯💡等）
- 口语化，像在跟朋友分享
- 有互动感，末尾可以带问句

## 结构特征
1. 开头钩子：一句话吸引注意（"最近发现..." "终于搞定..."）
2. 正文：2-4个点，每个点用emoji开头
3. 根据内容可以有两种路线：
   - 技术路线：展示方案/架构/效果
   - 体验路线：个人感受+推荐
4. 末尾：问句互动或总结 + 话题标签

## 字数控制
- 全文500-1000字
- 越短越好

## 绝对不要
- 不要大段文字
- 不要学术/正式语气
- 不要用"首先/其次/最后"
- 不要AI腔
"""
