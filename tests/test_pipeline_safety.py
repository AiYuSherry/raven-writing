import unittest

from personal_writing.core import pipeline


class PipelineSafetyTests(unittest.TestCase):
    def test_humanizer_tool_chatter_is_rejected(self):
        original = "你是不是也收到过 AI 写的稿子？读起来每个句子都对，但就是没人味。"
        chatter = """文件已读取。这份是 humanizer-zh skill 的完整定义。

请问你想让我做什么？
- 使用这份规则帮你润色某段文字
- 对规则本身提出修改建议
"""
        self.assertFalse(pipeline._is_valid_humanized_article(chatter, original))

    def test_humanizer_edit_commentary_is_rejected(self):
        original = "折腾了一晚上 cc-connect，把 AI 接上不同的聊天软件。"
        commentary = "这篇原文本身已经非常自然了，我们做了极轻的润色，主要是把几处略显公式化的地方拉回日常语气。"
        self.assertFalse(pipeline._is_valid_humanized_article(commentary, original))

    def test_headline_parser_accepts_common_numbered_formats(self):
        response = """## 标题候选
1. 折腾一晚接上AI — 公式：自由创作
2、同一工具两种体验
3) 微信卡在文件这步 - 公式：问题直给
4. 「Telegram顺太多了」 — 公式：反差
5. AI接到聊天软件后
"""
        candidates = pipeline._parse_headline_candidates(response)
        self.assertGreaterEqual(len(candidates), 5)
        self.assertEqual(candidates[0]["headline"], "折腾一晚接上AI")

    def test_custom_prompt_wrappers_are_removed(self):
        wrapped = """已读取文件内容。这是一个完整写作 prompt。

# 日常写作风格

像给朋友说话。

请问你想让我按照这个 prompt 做什么？"""
        cleaned = pipeline._sanitize_style_prompt_template(wrapped)
        self.assertIn("# 日常写作风格", cleaned)
        self.assertNotIn("已读取文件内容", cleaned)
        self.assertNotIn("请问你想让我", cleaned)

    def test_hard_cleanup_removes_banned_dash_and_contrast(self):
        text = "这不是工具的问题，而是流程的问题——需要修。"
        cleaned = pipeline._mechanical_hard_cleanup(text)
        self.assertNotIn("——", cleaned)
        self.assertNotIn("不是", cleaned)


if __name__ == "__main__":
    unittest.main()
