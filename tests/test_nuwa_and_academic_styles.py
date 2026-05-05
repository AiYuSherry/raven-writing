import json
import unittest
from unittest.mock import patch

from personal_writing.core import nuwa_distiller
from personal_writing.core.style_engine import StyleRegistry
from personal_writing.styles.daily import DailyStyle
from personal_writing.styles.zheng_ge_academic import ZhengGeAcademicStyle


class NuwaDistillerTests(unittest.TestCase):
    def test_safe_slug_rejects_pathlike_input(self):
        self.assertEqual(nuwa_distiller.safe_slug("../Bad Skill!!"), "bad-skill")
        self.assertTrue(nuwa_distiller.safe_slug("郑戈").startswith("distilled-skill-"))

    def test_parse_bundle_from_fenced_json(self):
        payload = {
            "skill_name": "demo-perspective",
            "warnings": ["材料较少"],
            "files": [{"path": "SKILL.md", "content": "---\nname: demo\n---\n# Demo"}],
        }
        bundle = nuwa_distiller.parse_bundle(
            "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```",
            "fallback",
        )
        self.assertEqual(bundle["skill_name"], "demo-perspective")
        self.assertEqual(bundle["files"][0]["path"], "SKILL.md")
        self.assertEqual(bundle["warnings"], ["材料较少"])

    def test_parse_bundle_falls_back_to_skill_md(self):
        bundle = nuwa_distiller.parse_bundle("# Plain Skill\n\nBody", "plain-skill")
        self.assertEqual(bundle["skill_name"], "plain-skill")
        self.assertEqual(bundle["files"][0]["path"], "SKILL.md")


class AcademicStyleTests(unittest.TestCase):
    def test_zheng_ge_style_metadata(self):
        style = ZhengGeAcademicStyle()
        self.assertEqual(style.name, "zheng_ge_academic")
        self.assertEqual(style.config["category"], "academic")
        self.assertEqual(style.config["structure"], "academic_paper")

    def test_registry_exposes_style_categories(self):
        registry = StyleRegistry()
        registry.register(DailyStyle)
        registry.register(ZhengGeAcademicStyle)
        with patch("personal_writing.core.style_engine.StyleRepo.get_by_name", return_value=None), \
             patch("personal_writing.core.style_engine.StyleRepo.list", return_value=[]):
            info = registry.list_info()
        categories = {item["name"]: item["category"] for item in info}
        self.assertEqual(categories["daily"], "general")
        self.assertEqual(categories["zheng_ge_academic"], "academic")


if __name__ == "__main__":
    unittest.main()
