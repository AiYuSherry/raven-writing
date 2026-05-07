import unittest
from unittest import mock

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

    def test_humanizer_prompt_stays_compact(self):
        original = "折腾了一晚上 cc-connect，把 AI 接上不同的聊天软件。体验差太多了。"
        captured = {}

        def fake_call(prompt):
            captured["prompt"] = prompt
            return original

        long_skill = "\n".join([f"- AI 写作规则 {i}: 删除公式感和破折号" for i in range(300)])
        with mock.patch.object(pipeline, "_load_humanizer_skill", return_value=long_skill), \
             mock.patch.object(pipeline.claude_client, "is_available", return_value=True), \
             mock.patch.object(pipeline.claude_client, "call", side_effect=fake_call):
            result = pipeline._humanize(original, "short_science", examples=[
                {"title": "参考", "content": "这是一个很长的参考。" * 500}
            ])

        self.assertEqual(result, original)
        self.assertLess(len(captured["prompt"]), 9000)
        self.assertNotIn("下面是旧版内置规则", captured["prompt"])
        self.assertLessEqual(captured["prompt"].count("这是一个很长的参考。"), 16)

    def test_passthrough_style_detection(self):
        class DummyStyle:
            name = "什么都不改"
            display_name = "什么都不改"
            description = "用于排版推送"

            def get_config(self):
                return {"prompt_template": "对于输入的内容，不做任何修改"}

        self.assertTrue(pipeline._is_passthrough_style(DummyStyle()))

    def test_passthrough_article_keeps_content(self):
        content = "# 标题\n\n第一段。\n\n![图](a.png)\n\n第二段。"
        article = pipeline._passthrough_article(content, "")
        self.assertEqual(article["content"], content)
        self.assertEqual(article["title"], "标题")
        self.assertTrue(article["passthrough"])
        self.assertIn({"headline": "标题", "formula": "原文标题"}, article["headline_candidates"])

    def test_passthrough_title_falls_back_to_source_title(self):
        article = pipeline._passthrough_article("\n\n![图](a.png)\n\n" + ("很长" * 60), "source.md")
        self.assertEqual(article["title"], "source.md")

    def test_passthrough_generates_local_tutorial_headlines(self):
        article = pipeline._passthrough_article(
            "# 手把手教会你：Agent 接入 Telegram\n\n正文。",
            "",
        )
        headlines = [c["headline"] for c in article["headline_candidates"]]
        self.assertIn("Agent接入Telegram教程", headlines)
        self.assertIn("怎么Agent接入Telegram", headlines)

    def test_headline_prompt_requires_plain_tutorial_titles(self):
        captured = {}

        def fake_call(prompt):
            captured["prompt"] = prompt
            return """## 标题候选
1. 怎么把Claude接到Telegram — 公式：教程直说
2. 如何用Telegram收AI消息 — 公式：教程直说
3. Telegram接AI的方法 — 公式：教程直说
4. 5分钟搞定AI消息桥 — 公式：干货承诺
5. 微信发不了就换Telegram — 公式：自由创作
"""

        with mock.patch.object(pipeline.claude_client, "is_available", return_value=True), \
             mock.patch.object(pipeline.claude_client, "call", side_effect=fake_call):
            candidates = pipeline.generate_headline_candidates(
                "这是一篇教程，教你把 Claude 接到 Telegram。",
                "先配置 bot token，再设置 webhook。",
                "custom_tutorial",
            )

        self.assertGreaterEqual(len(candidates), 5)
        self.assertIn("教程直说", captured["prompt"])
        self.assertIn("必须至少给 2 个", captured["prompt"])
        self.assertEqual(candidates[0]["formula"], "教程直说")


if __name__ == "__main__":
    unittest.main()
