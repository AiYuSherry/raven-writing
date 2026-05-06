"""Nuwa skill distillation service for the writing desk."""

import json
import os
import re
import subprocess
import uuid

from ..db.repository import StyleRepo
from ..utils import claude_client


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DISTILLED_ROOT = os.path.join(PROJECT_ROOT, "skills", "distilled")
NUWA_ROOT = os.path.expanduser("~/.codex/skills/nuwa-skill")
NUWA_SKILL_PATH = os.path.join(NUWA_ROOT, "SKILL.md")
QUALITY_CHECK = os.path.join(NUWA_ROOT, "scripts", "quality_check.py")

TARGET_TYPE_LABELS = {
    "person": "人物/主题",
    "academic_author": "学术作者",
    "project": "项目/GitHub或本地项目",
}


def safe_slug(value, fallback="distilled-skill"):
    """Return a filesystem/style safe ASCII slug."""
    raw = (value or "").strip().lower()
    raw = re.sub(r"[\s_]+", "-", raw)
    slug = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = f"{fallback}-{uuid.uuid4().hex[:8]}"
    return slug[:72].strip("-") or fallback


def style_name_from_skill(skill_name):
    """Convert a skill directory/name into a DB style identifier."""
    base = safe_slug(skill_name, "distilled-style").replace("-", "_")
    if not base.endswith("_style"):
        base += "_style"
    return base[:90]


def strip_frontmatter(text):
    return re.sub(r"^---[\s\S]*?---\s*", "", text or "").strip()


def extract_frontmatter_name(text):
    m = re.search(r"^---[\s\S]*?^name:\s*['\"]?([^'\"\n]+)['\"]?\s*$", text or "", flags=re.MULTILINE)
    if m:
        return safe_slug(m.group(1), "distilled-skill")
    return ""


def _read(path, limit=None):
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if limit and len(text) > limit:
        return text[:limit].rstrip() + "\n\n[内容已截断]"
    return text


def _load_template(target_type):
    rel = "references/skill-template.md"
    if target_type == "academic_author":
        rel = "references/academic-author-template.md"
    elif target_type == "project":
        rel = "templates/project/SKILL.md.template"
    return _read(os.path.join(NUWA_ROOT, rel), limit=14000)


def _extract_json(text):
    """Parse the model bundle JSON, tolerating fenced code blocks."""
    text = (text or "").strip()
    candidates = []
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    candidates.extend(part.strip() for part in fenced)
    candidates.append(text)
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("模型没有返回可解析的 JSON bundle")


def parse_bundle(raw_output, fallback_skill_name):
    """Return a normalized skill bundle from model output."""
    try:
        data = _extract_json(raw_output)
    except ValueError:
        return {
            "skill_name": safe_slug(fallback_skill_name, "distilled-skill"),
            "files": [{"path": "SKILL.md", "content": raw_output.strip()}],
            "warnings": ["模型未返回 JSON，已把原始输出保存为 SKILL.md。"],
        }

    skill_name = safe_slug(data.get("skill_name") or fallback_skill_name, "distilled-skill")
    files = data.get("files") or []
    if not isinstance(files, list):
        raise ValueError("bundle.files 必须是数组")
    normalized = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = (item.get("path") or "").strip()
        content = item.get("content")
        if not path or content is None:
            continue
        normalized.append({"path": path, "content": str(content)})
    if not any(f["path"] == "SKILL.md" for f in normalized):
        skill_md = data.get("skill_md") or data.get("skill") or ""
        if skill_md:
            normalized.insert(0, {"path": "SKILL.md", "content": str(skill_md)})
    if not any(f["path"] == "SKILL.md" for f in normalized):
        raise ValueError("bundle 缺少 SKILL.md")
    return {
        "skill_name": skill_name,
        "files": normalized,
        "warnings": list(data.get("warnings") or []),
    }


def _safe_dest(skill_dir, rel_path):
    rel = os.path.normpath((rel_path or "").replace("\\", "/")).lstrip("/")
    if rel.startswith("../") or rel == ".." or os.path.isabs(rel):
        raise ValueError(f"非法文件路径: {rel_path}")
    dest = os.path.abspath(os.path.join(skill_dir, rel))
    root = os.path.abspath(skill_dir)
    if dest != root and not dest.startswith(root + os.sep):
        raise ValueError(f"非法文件路径: {rel_path}")
    return dest


def write_bundle(bundle):
    """Write a skill bundle under skills/distilled without overwriting."""
    os.makedirs(DISTILLED_ROOT, exist_ok=True)
    skill_dir = os.path.abspath(os.path.join(DISTILLED_ROOT, bundle["skill_name"]))
    root = os.path.abspath(DISTILLED_ROOT)
    if not skill_dir.startswith(root + os.sep):
        raise ValueError("非法 skill 输出目录")
    if os.path.exists(skill_dir):
        raise FileExistsError(f"蒸馏目录已存在: {skill_dir}")
    for item in bundle["files"]:
        dest = _safe_dest(skill_dir, item["path"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(item["content"].rstrip() + "\n")
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        raise ValueError("写入后未找到 SKILL.md")
    return skill_dir


def run_quality_check(skill_dir):
    if not os.path.isfile(QUALITY_CHECK):
        return {"status": "skipped", "output": "未找到女娲 quality_check.py"}
    try:
        result = subprocess.run(
            ["python3", QUALITY_CHECK, skill_dir],
            capture_output=True,
            text=True,
            timeout=25,
        )
        return {
            "status": "passed" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "output": ((result.stdout or "") + (result.stderr or "")).strip()[:4000],
        }
    except Exception as e:
        return {"status": "error", "output": str(e)}


def _build_prompt(target_type, target_name, purpose, materials, path="", url=""):
    nuwa_skill = _read(NUWA_SKILL_PATH, limit=26000)
    template = _load_template(target_type)
    label = TARGET_TYPE_LABELS.get(target_type, "人物/主题")
    default_skill_name = _default_skill_name(target_type, target_name)
    return f"""{nuwa_skill}

## 本次任务：为乌鸦写作台生成可落地 Skill

对象类型：{label}
对象名称：{target_name}
用途说明：{purpose or "作为写作台可复用的写作/分析风格"}
本地路径：{path or "无"}
URL：{url or "无"}

## 参考模板
{template}

## 用户材料
{materials or "无额外材料。"}

## 输出要求
请直接输出一个 JSON 对象，不要输出 Markdown 解释。JSON 结构必须是：
{{
  "skill_name": "{default_skill_name}",
  "warnings": [],
  "files": [
    {{"path": "SKILL.md", "content": "完整 SKILL.md 内容"}},
    {{"path": "references/research/source-boundaries.md", "content": "可选材料"}}
  ]
}}

硬性规则：
- 至少包含 `SKILL.md`。
- `SKILL.md` 必须有 frontmatter，包含 name 和 description。
- 文件路径只能是相对路径，不能包含 `..`，不能是绝对路径。
- 不要留下 TODO、TBD、xxx、待补充等占位符。
- 这是给乌鸦写作台使用的 skill；如果信息不足，请在 warnings 中说明边界，但仍生成可用的最小 skill。
"""


def _default_skill_name(target_type, target_name):
    base = safe_slug(target_name, "distilled")
    if target_type == "academic_author":
        return f"{base}-academic-author"
    if target_type == "project":
        return f"{base}-project-skill"
    return f"{base}-perspective"


def create_style_from_skill(skill_dir, display_name, description=""):
    """Create a DB custom style from a distilled SKILL.md."""
    skill_path = os.path.join(skill_dir, "SKILL.md")
    skill_text = _read(skill_path)
    frontmatter_name = extract_frontmatter_name(skill_text)
    style_name = style_name_from_skill(frontmatter_name or os.path.basename(skill_dir))
    if StyleRepo.get_by_name(style_name):
        raise ValueError(f"风格标识已存在: {style_name}")
    prompt_template = strip_frontmatter(skill_text)
    config = {
        "prompt_template": prompt_template,
        "word_count": 1800,
        "tone": "distilled",
        "structure": "skill_driven",
        "personal_pronoun": "mixed",
        "category": "custom",
        "source_skill_dir": skill_dir,
    }
    StyleRepo.create(
        style_name,
        display_name or os.path.basename(skill_dir),
        description or "女娲蒸馏生成的写作风格",
        config,
        is_builtin=0,
    )
    return style_name, prompt_template


def distill(target_type, target_name, purpose="", materials="", path="", url="", add_to_styles=True):
    target_type = target_type if target_type in TARGET_TYPE_LABELS else "person"
    target_name = (target_name or "").strip()
    if not target_name:
        raise ValueError("请填写蒸馏对象名称")
    if not claude_client.is_available():
        raise RuntimeError("Claude Code CLI not found. Install it first.")

    prompt = _build_prompt(target_type, target_name, purpose, materials, path=path, url=url)
    raw_output = claude_client.call(prompt, max_retries=0)
    bundle = parse_bundle(raw_output, _default_skill_name(target_type, target_name))
    if add_to_styles:
        skill_text = next((f["content"] for f in bundle["files"] if f["path"] == "SKILL.md"), "")
        intended_style_name = style_name_from_skill(extract_frontmatter_name(skill_text) or bundle["skill_name"])
        if StyleRepo.get_by_name(intended_style_name):
            raise ValueError(f"风格标识已存在: {intended_style_name}")
    skill_dir = write_bundle(bundle)
    quality = run_quality_check(skill_dir)

    style_name = ""
    prompt_template = ""
    if add_to_styles:
        style_name, prompt_template = create_style_from_skill(
            skill_dir,
            f"{target_name}（女娲蒸馏）",
            f"{TARGET_TYPE_LABELS.get(target_type, '对象')}蒸馏生成的写作风格",
        )

    return {
        "status": "ok",
        "skill_name": bundle["skill_name"],
        "skill_dir": skill_dir,
        "style_name": style_name,
        "prompt_template": prompt_template,
        "quality_check": quality,
        "warnings": bundle.get("warnings", []),
    }
