import unittest
from unittest.mock import patch

from personal_writing.utils.md_to_txt import markdown_to_txt


class MarkdownToTxtTests(unittest.TestCase):
    def test_converts_tutorial_markdown_to_plain_text(self):
        markdown = """# Telegram 接入 Claude Code教程（cc-connect）

## 为什么用 Telegram？

1. **多 Agent 支持**：可以连接多个 Agent

- 每个实例是一个独立的 Claude Code 会话

> **注意**：Token 不要泄露。

```bash
TELEGRAM_BOT_TOKEN=你的TOKEN cc-connect
```

| 操作 | 说明 |
| --- | --- |
| 文字聊天 | 直接发消息给 bot |
"""
        txt = markdown_to_txt(markdown)
        self.assertIn("Telegram 接入 Claude Code教程（cc-connect）", txt)
        self.assertIn("1. 多 Agent 支持：可以连接多个 Agent", txt)
        self.assertIn("每个实例是一个独立的 Claude Code 会话", txt)
        self.assertIn("注意：Token 不要泄露。", txt)
        self.assertIn("TELEGRAM_BOT_TOKEN=你的TOKEN cc-connect", txt)
        self.assertIn("操作：文字聊天", txt)
        self.assertIn("说明：直接发消息给 bot", txt)
        self.assertNotIn("**", txt)
        self.assertNotIn("```", txt)
        self.assertNotIn("| --- |", txt)

    def test_format_page_and_api(self):
        from personal_writing.web.app import create_app

        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        page = client.get("/format")
        self.assertEqual(page.status_code, 200)
        self.assertIn("格式转换", page.get_data(as_text=True))
        self.assertIn("Markdown 转 TXT", page.get_data(as_text=True))
        self.assertIn("一键排版", page.get_data(as_text=True))
        self.assertIn("推送公众号", page.get_data(as_text=True))
        self.assertIn("存档", page.get_data(as_text=True))

        response = client.post("/api/v1/format/markdown-to-txt", json={
            "text": "# 标题\n\n**重点**"
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["text"].strip(), "标题\n\n重点")

        with patch("personal_writing.web.app.archive_to_works", return_value="/tmp/标题.md") as archive:
            archived = client.post("/api/v1/format/archive", json={
                "text": "# 标题\n\n正文"
            })
        self.assertEqual(archived.status_code, 200)
        archive.assert_called_once()
        archive_data = archived.get_json()
        self.assertEqual(archive_data["status"], "ok")
        self.assertEqual(archive_data["title"], "标题")


if __name__ == "__main__":
    unittest.main()
