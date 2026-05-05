#!/usr/bin/env python3
"""Package a clean distribution copy of 乌鸦写作台.

Usage:
    python scripts/package.py

Output:
    ../乌鸦写作台-packaged/  (alongside the project dir)

This script copies source files and strips personal information while
preserving the original project untouched.
"""

import os
import re
import json
import shutil
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(os.path.dirname(PROJECT_DIR), "乌鸦写作台-packaged")

# ── 外部 skill 路径 ──────────────────────────────────────────────────
WECHAT_TYPESET_SKILL = os.path.expanduser("~/.claude/skills/wechat-typeset-pro")

EXCLUDE_PATTERNS = ["__pycache__", "*.pyc", "*.pyo", "*.egg-info", ".DS_Store"]
IGNORED_PROMPTS = set()

STYLE_ENGINE_ADDITIONS = '''
import os
import pathlib


def _get_prompts_dir():
    """Locate the prompts directory.

    Checks in order:
    1. WRITING_STYLES_DIR env var
    2. ../prompts/ relative to project root
    3. ./prompts/ relative to cwd
    """
    env_dir = os.environ.get("WRITING_STYLES_DIR")
    if env_dir:
        return env_dir
    this_file = pathlib.Path(__file__).resolve()
    project_root = this_file.parent.parent.parent.parent
    prompts_dir = project_root / "prompts"
    if prompts_dir.is_dir():
        return str(prompts_dir)
    return os.path.join(os.getcwd(), "prompts")


def load_prompt_from_file(style_name):
    """Load a prompt template from prompts/{style_name}.md."""
    path = os.path.join(_get_prompts_dir(), f"{style_name}.md")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    return None
'''


def copy_source():
    """Copy src/ excluding caches."""
    src_dir = os.path.join(PROJECT_DIR, "src")
    dst_dir = os.path.join(OUTPUT_DIR, "src")
    shutil.copytree(src_dir, dst_dir, ignore=shutil.ignore_patterns(*EXCLUDE_PATTERNS))
    # Also clean any stray .pyc
    for root, dirs, files in os.walk(dst_dir):
        for f in files:
            if f.endswith(".pyc"):
                os.remove(os.path.join(root, f))


def strip_style_prompt(style_name):
    """Remove hardcoded get_prompt_template from a style file."""
    filepath = os.path.join(
        OUTPUT_DIR, "src", "personal_writing", "styles", f"{style_name}.py"
    )
    if not os.path.isfile(filepath):
        return

    with open(filepath, "r") as f:
        content = f.read()

    # Remove everything from 'def get_prompt_template' to the closing triple-quote
    new_content = re.sub(
        r'    def get_prompt_template\(self\):\n        return """.*?"""',
        "",
        content,
        flags=re.DOTALL,
    )

    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)
        print(f"  [strip] {style_name}.py: removed built-in prompt")
    else:
        print(f"  [warn] {style_name}.py: could not find prompt to strip")


def patch_sherry():
    """Clean sherry.py: remove SKILL.md loader, add external prompt fallback."""
    filepath = os.path.join(
        OUTPUT_DIR, "src", "personal_writing", "styles", "sherry.py"
    )
    with open(filepath, "r") as f:
        content = f.read()

    content = content.replace("import os\nimport re\n\n", "")
    content = re.sub(r"\nSKILL_PATHS = \[[\s\S]*?\]\n\n", "\n", content, count=1)
    content = re.sub(r"\ndef _load_skill_prompt\(\):[\s\S]*?return None\n\n", "\n", content, count=1)
    content = content.replace("    _skill_prompt = None\n", "")
    content = re.sub(
        r"    def get_prompt_template\(self\):[\s\S]*?\n\n\nregistry.register\(SherryStyle\)",
        """    def get_prompt_template(self):
        from ..core.style_engine import load_prompt_from_file
        prompt = load_prompt_from_file(self.name)
        if prompt:
            return prompt
        return f\"请按照{self.display_name}的风格写一篇文章。\"


registry.register(SherryStyle)""",
        content,
        count=1,
    )

    with open(filepath, "w") as f:
        f.write(content)
    print("  [patch] sherry.py: replaced with external prompt loader")


def patch_style_methods_to_external_prompts():
    """Make built-in styles prefer external prompt files."""
    for style_name in ("daily", "short_science", "xiaohongshu"):
        filepath = os.path.join(
            OUTPUT_DIR, "src", "personal_writing", "styles", f"{style_name}.py"
        )
        if not os.path.isfile(filepath):
            continue
        with open(filepath, "r") as f:
            content = f.read()
        if "load_prompt_from_file" in content:
            continue
        replacement = """
    def get_prompt_template(self):
        from ..core.style_engine import load_prompt_from_file
        prompt = load_prompt_from_file(self.name)
        if prompt:
            return prompt
        return f"请按照{self.display_name}的风格写一篇文章。"
"""
        new_content = re.sub(
            r"\n    def get_prompt_template\(self\):\n        return \"\"\".*?\"\"\"",
            "\n" + replacement.rstrip(),
            content,
            flags=re.DOTALL,
            count=1,
        )
        if new_content != content:
            with open(filepath, "w") as f:
                f.write(new_content)
            print(f"  [patch] {style_name}.py: prompt loads from prompts/{style_name}.md")


def add_style_engine_loader():
    """Add load_prompt_from_file to style_engine.py."""
    filepath = os.path.join(
        OUTPUT_DIR, "src", "personal_writing", "core", "style_engine.py"
    )
    with open(filepath, "r") as f:
        content = f.read()

    # Insert before "class BaseStyle:"
    content = content.replace(
        "class BaseStyle:",
        STYLE_ENGINE_ADDITIONS + "\n\nclass BaseStyle:",
        1,
    )
    with open(filepath, "w") as f:
        f.write(content)
    print("  [patch] style_engine.py: added external prompt loader")


def patch_db_path():
    """Make DB_DIR portable: resolve relative to project root."""
    filepath = os.path.join(
        OUTPUT_DIR, "src", "personal_writing", "db", "schema.py"
    )
    with open(filepath, "r") as f:
        content = f.read()

    old = 'DB_DIR = os.path.expanduser("~/Desktop/计算机/个人写作/data")'
    new = (
        'def _writing_data_dir():\n'
        '    env = os.environ.get("PERSONAL_WRITING_DATA")\n'
        '    if env:\n'
        '        return env\n'
        '    base = os.path.dirname(os.path.dirname(\n'
        '        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))\n'
        '    return os.path.join(base, "data")\n'
        '\n'
        '\n'
        'DB_DIR = _writing_data_dir()'
    )
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    print("  [patch] schema.py: DB_DIR now resolves relative to project root / env var")


def patch_skill_paths():
    """Make app paths portable."""
    filepath = os.path.join(
        OUTPUT_DIR, "src", "personal_writing", "web", "app.py"
    )
    with open(filepath, "r") as f:
        content = f.read()

    # 1. Add _get_project_root() and _skill_dir() helpers after TEMPLATE_DIR line
    helpers = '''
def _get_project_root():
    """Project root: env var override, or resolve from app.py location."""
    env = os.environ.get("PERSONAL_WRITING_ROOT")
    if env:
        return env
    # app.py -> web/ -> personal_writing/ -> src/ -> project root
    return os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _skill_dir():
    """Get wechat-typeset-pro skill directory."""
    env = os.environ.get("WECHAT_TYPESET_DIR")
    if env:
        return env
    return os.path.join(_get_project_root(), "skills", "wechat-typeset-pro")
'''

    content = content.replace(
        "TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), \"templates\")",
        "TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), \"templates\")" + helpers,
    )

    content = content.replace(
        'UPLOAD_DIR = os.path.expanduser("~/Desktop/计算机/个人写作/data/uploads")',
        'UPLOAD_DIR = os.path.join(_get_project_root(), "data", "uploads")',
    )
    content = content.replace(
        'OBSIDIAN_VAULT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault")',
        'OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT_PATH") or os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault")',
    )

    # 2. Replace hardcoded skill config paths
    content = content.replace(
        'config_path = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/config.json")',
        'config_path = os.path.join(_skill_dir(), "config.json")',
    )
    content = content.replace(
        'format_script = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/scripts/format.py")',
        'format_script = os.path.join(_skill_dir(), "scripts", "format.py")',
    )
    content = content.replace(
        'publish_script = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/scripts/publish.py")',
        'publish_script = os.path.join(_skill_dir(), "scripts", "publish.py")',
    )
    content = content.replace(
        'skill_config = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/config.json")',
        'skill_config = os.path.join(_skill_dir(), "config.json")',
    )

    with open(filepath, "w") as f:
        f.write(content)
    print("  [patch] app.py: data, obsidian, and skill paths now portable")

    # Re-read for the SAVE_DIR change (content was written above)
    with open(filepath, "r") as f:
        content = f.read()
    content = content.replace(
        'SAVE_DIR = os.path.expanduser("~/WorkBuddy/wechat-typeset-pro")',
        'SAVE_DIR = os.path.join(_get_project_root(), "output")',
    )
    with open(filepath, "w") as f:
        f.write(content)
    print("  [patch] app.py: SAVE_DIR now uses ./output/ relative to project root")


def patch_obsidian_bridge():
    """Make vault path and archive output configurable via env vars."""
    filepath = os.path.join(
        OUTPUT_DIR, "src", "personal_writing", "core", "obsidian_bridge.py"
    )
    with open(filepath, "r") as f:
        content = f.read()

    # 1. Make VAULT_PATH configurable via env var
    old_vault = (
        'VAULT_PATH = os.path.expanduser(\n'
        '    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"\n'
        ')'
    )
    new_vault = (
        'VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH") or os.path.expanduser(\n'
        '    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"\n'
        ')'
    )
    content = content.replace(old_vault, new_vault)

    # 2. Add ARCHIVE_OUTPUT_DIR override — if set, bypass VAULT_PATH entirely
    old_works = (
        'WORKS_FOLDER = os.path.join(VAULT_PATH, "我的作品")'
    )
    new_works = (
        'ARCHIVE_OUTPUT_DIR = os.environ.get("ARCHIVE_OUTPUT_DIR")\n'
        'if ARCHIVE_OUTPUT_DIR:\n'
        '    WORKS_FOLDER = ARCHIVE_OUTPUT_DIR\n'
        'else:\n'
        '    WORKS_FOLDER = os.path.join(VAULT_PATH, "我的作品")'
    )
    content = content.replace(old_works, new_works)

    with open(filepath, "w") as f:
        f.write(content)
    print("  [patch] obsidian_bridge.py: vault path + archive dir via env vars")


def patch_wechat_footer():
    """Make WeChat footer configurable via env var."""
    filepath = os.path.join(
        OUTPUT_DIR, "src", "personal_writing", "web", "app.py"
    )
    with open(filepath, "r") as f:
        content = f.read()

    old = (
        "'<font color=\"#808080\"><i>关注公众号律海流深，获取更多 AI 实操经验。</i></font>'"
    )
    new = (
        "f'<font color=\"#808080\"><i>关注公众号{os.environ.get(\"BLOG_NAME\", \"律海流深\")}，获取更多 AI 实操经验。</i></font>'"
    )
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    print("  [patch] app.py: WeChat footer configurable via BLOG_NAME env var")


def patch_cover_image():
    """Make cover image path configurable via env var with generic fallback."""
    filepath = os.path.join(
        OUTPUT_DIR, "src", "personal_writing", "web", "app.py"
    )
    with open(filepath, "r") as f:
        content = f.read()

    # Replace the entire default_cover block — wrap with env var + generic fallback
    old_block = (
        '        default_cover = os.path.expanduser(\n'
        '            "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"\n'
        '            "/我的作品/图片素材/公众号封面（没有指定封面就用这张）.png"\n'
        '        )'
    )
    new_block = (
        '        default_cover = os.environ.get("WECHAT_COVER_IMAGE") or os.path.expanduser(\n'
        '            "~/Pictures/wechat-cover.png"\n'
        '        )'
    )
    content = content.replace(old_block, new_block, 1)
    with open(filepath, "w") as f:
        f.write(content)
    print("  [patch] app.py: cover image configurable via WECHAT_COVER_IMAGE env var")


def copy_misc():
    """Copy setup.py, launchers, and public prompts. Write custom .env.example."""
    shutil.copy2(
        os.path.join(PROJECT_DIR, "setup.py"),
        os.path.join(OUTPUT_DIR, "setup.py"),
    )
    for name in ("start-web.sh", "启动网站.command"):
        src = os.path.join(PROJECT_DIR, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUTPUT_DIR, name))

    # Write custom .env.example with all portable env vars documented
    env_example = """# Personal Writing Platform — Environment Configuration
# Copy to .env and adjust for your local setup.

# Project root (auto-detected from file path in editable install; set manually for regular install)
# PERSONAL_WRITING_ROOT=

# Database directory (default: {project_root}/data/)
# PERSONAL_WRITING_DATA=

# Path to your Obsidian vault (default: auto-detected)
# OBSIDIAN_VAULT_PATH=

# Archive output directory (overrides vault path — set this to save articles anywhere)
# ARCHIVE_OUTPUT_DIR=

# Directory containing style prompt files (default: ./prompts/)
# WRITING_STYLES_DIR=

# Path to wechat-typeset-pro skill (default: ./skills/wechat-typeset-pro/)
# WECHAT_TYPESET_DIR=

# WeChat Official Account name (for article footers). Leave empty for no footer.
# BLOG_NAME=

# Default cover image path for WeChat publishing
# WECHAT_COVER_IMAGE=
"""
    with open(os.path.join(OUTPUT_DIR, ".env.example"), "w", encoding="utf-8") as f:
        f.write(env_example)
    print("  [write] .env.example")

    prompts_dir = os.path.join(OUTPUT_DIR, "prompts")
    os.makedirs(prompts_dir, exist_ok=True)
    src_prompts = os.path.join(PROJECT_DIR, "prompts")
    for fname in sorted(os.listdir(src_prompts)):
        if not fname.endswith(".md") or fname in IGNORED_PROMPTS:
            continue
        shutil.copy2(os.path.join(src_prompts, fname), os.path.join(prompts_dir, fname))
        print(f"  [copy] prompts/{fname}")


def copy_wechat_skill():
    """Copy wechat-typeset-pro skill and clean personal info."""
    skill_dst = os.path.join(OUTPUT_DIR, "skills", "wechat-typeset-pro")
    shutil.copytree(
        WECHAT_TYPESET_SKILL,
        skill_dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )

    # Clean config.json — reset personal paths
    config_path = os.path.join(skill_dst, "config.json")
    with open(config_path, "r") as f:
        cfg = json.load(f)
    cfg["vault_root"] = "~"
    cfg["output_dir"] = "~/output/wechat-typeset-pro"
    cfg["cover"]["output_dir"] = "~/output/wechat-typeset-pro/covers"
    cfg["cover"]["default_image"] = ""
    cfg["cover"]["image_generation_script"] = ""
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print("  [clean] wechat-typeset-pro/config.json: reset personal paths")

    # Clean SKILL.md — replace personal image paths with placeholder
    skill_md = os.path.join(skill_dst, "SKILL.md")
    with open(skill_md, "r") as f:
        content = f.read()
    # Replace personal Obsidian vault paths (containing username + full path)
    content = content.replace(
        "/Users/huziyang/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault",
        "~/path/to/your/vault",
    )
    # Replace WorkBuddy references
    content = content.replace("~/WorkBuddy/wechat-typeset-pro", "~/output/wechat-typeset-pro")
    content = content.replace("'WorkBuddy', 'wechat-typeset-pro'", "'output', 'wechat-typeset-pro'")
    content = content.replace("WorkBuddy/wechat-typeset-pro", "output/wechat-typeset-pro")
    # Replace personalized folder structure in cover image paths
    content = re.sub(
        r"~/path/to/your/vault/[^\n]*?\.(?:png|jpg|jpeg)",
        "~/path/to/your/cover-image.png",
        content,
    )
    with open(skill_md, "w") as f:
        f.write(content)
    print("  [clean] wechat-typeset-pro/SKILL.md: replaced personal paths")

    # Remove skillhub meta (not needed)
    meta_path = os.path.join(skill_dst, "_skillhub_meta.json")
    if os.path.isfile(meta_path):
        os.remove(meta_path)


def write_readme():
    """Write README.md."""
    readme = r"""# 乌鸦写作台

乌鸦写作台是一个本地优先的 AI 写作工作台。它把素材导入、风格生成、文章修改、标题训练、Obsidian 存档、微信公众号排版和推送放在同一个界面里，适合公众号长文、日常随笔、短科普、小红书笔记等多平台写作。

它的核心目标不是做一个通用聊天框，而是把一套个人写作流程固定下来：上传素材，选择风格，生成初稿，挑标题，反复修改，存档复盘，最后排版发布。

## 核心功能

### 写作台

- 支持粘贴文本、上传文件和导入多种素材格式。
- 可同时选择多个写作风格生成不同版本文章。
- 每篇生成结果会显示对应风格，方便单独查看、修改和存档。
- 支持文章继续修改、采纳修改结果，并保留修改要求和系统识别到的改动。
- 内置硬约束清洗，避免生成破折号、固定 AI 句式和跨风格串味。

### 风格系统

- 内置四类基础风格：卡兹克（公众号长文）、日常、短科普、小红书。
- 支持通过上传自己的作品或 SKILL.md 创建新风格。
- 风格页可以查看和编辑 prompt、参考素材、风格说明。
- 内部仍使用 `sherry` 作为卡兹克公众号长文风格的兼容标识，运行时继续走 Sherry skill。

### 标题工坊

- 根据文章内容自动生成多组候选标题。
- 支持保存平时积累的好标题，按类别管理。
- 支持批量添加、编辑、删除标题样本。
- AI 可以分析标题库，总结标题规律，并把提炼出的模式加入标题公式库，供下次生成时复用。

### 写作回顾与统计

- 记录历史素材、生成任务、文章版本和修改记录。
- 存档后保留原稿和终稿，便于回顾修改差异。
- 自动统计写作数量、风格分布等数据。
- 最近任务可以隐藏，截图或演示时更不容易暴露隐私。

### Obsidian 存档

- 生成文章可以导出为 Markdown。
- 支持存档到 Obsidian vault，也可以通过环境变量改到任意目录。
- 存档路径、数据库路径和排版输出路径都可以配置，方便迁移和分发。

### 微信公众号排版与推送

- 内置 `wechat-typeset-pro` 排版 skill。
- 支持 Markdown 转微信公众号兼容 HTML。
- 支持多主题预览，选定效果后推送到公众号草稿箱。
- 公众号 AppID、AppSecret、作者和封面图都通过设置页或环境变量配置，打包版本不会附带真实凭证。

## 目录结构

```
├── src/personal_writing/      # 源码
│   ├── core/                  # 核心引擎（风格管理、写作流水线、Obsidian 桥接）
│   ├── styles/                # 写作风格定义（卡兹克、日常、短科普、小红书）
│   ├── db/                    # SQLite 数据库
│   ├── cli/                   # 命令行入口
│   ├── web/                   # Web 界面（Flask）
│   └── utils/                 # 工具（Claude Code 调用等）
├── prompts/                   # 写作风格 prompt（外部可配置）
│   └── sherry.md              # 卡兹克公众号长文风格（公开）
├── skills/
│   └── wechat-typeset-pro/    # 微信公众号排版引擎
│       ├── scripts/
│       │   ├── format.py      # Markdown → 微信兼容 HTML
│       │   └── publish.py     # HTML → 公众号草稿箱
│       └── themes/            # 30 套排版主题
├── requirements.txt
├── setup.py
└── .env.example
```

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
# 或
pip install -e .
```

### 2. 配置 Claude Code

乌鸦写作台默认调用 Claude Code CLI 作为写作引擎。请确保已安装：

```bash
npm install -g @anthropic-ai/claude-code
```

### 3. 启动 Web 界面

```bash
python -m personal_writing.web.app
# 或
personal-writing web
```

浏览器打开 `http://localhost:5000`。

### 4. 配置写作风格

写作风格 prompt 存储在 `prompts/` 目录下，每个文件对应一个风格。打包版已内置四种基础风格：卡兹克（公众号长文）、日常、短科普、小红书。

你也可以通过 Web 界面的「风格」页面创建更多自定义风格：上传 SKILL.md 文件、上传参考作品，或手动填写 prompt 模板。

| 文件 | 风格 | 说明 |
|------|------|------|
| `prompts/sherry.md` | 卡兹克（公众号长文） | 内置 |
| `prompts/daily.md` | 日常随笔 | 内置 |
| `prompts/short_science.md` | 短科普 | 内置 |
| `prompts/xiaohongshu.md` | 小红书笔记 | 内置 |

### 5. 命令行使用（可选）

```bash
# 从文本生成文章
echo "你的素材" | personal-writing --style sherry

# 从文件生成
personal-writing --input article.md --style daily
```

## 常用工作流

### 从素材到文章

1. 在「写作台」粘贴文本或上传文件。
2. 选择一个或多个风格。
3. 生成初稿后，在对应风格结果下继续修改。
4. 选定标题或自定义标题。
5. 导出 Markdown，或存档到 Obsidian。

### 从参考作品到新风格

1. 进入「风格」页面。
2. 上传参考文章、SKILL.md 或其他写作素材。
3. 让 AI 按现有写作 skill 的结构分析语气、结构、禁区和输出要求。
4. 保存为新风格后，就可以在写作台里直接选择使用。

### 从好标题到标题公式

1. 平时刷到好标题时，进入「标题工坊」保存下来，并按主题或平台标注类别。
2. 可以单条添加，也可以批量粘贴一组标题。
3. 定期让 AI 分析标题库，提炼常见结构、情绪钩子和表达模式。
4. 将有效模式加入标题公式库。
5. 之后生成文章标题时，系统会参考这些标题公式，候选标题质量会越来越贴近你的语感和平台需求。

### 从文章到公众号草稿

1. 生成或粘贴一篇 Markdown 文章。
2. 进入排版预览，选择合适主题。
3. 在「设置」页配置公众号凭证。
4. 推送到公众号草稿箱，进入后台继续检查和发布。

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `WRITING_STYLES_DIR` | 风格 prompt 目录路径 | `./prompts/` |
| `PERSONAL_WRITING_ROOT` | 项目根目录（安装为包时须设置） | 自动从文件路径解析 |
| `PERSONAL_WRITING_DATA` | 数据库目录 | `{project_root}/data` |
| `OBSIDIAN_VAULT_PATH` | Obsidian vault 路径 | 自动检测默认路径 |
| `ARCHIVE_OUTPUT_DIR` | 文章存档输出目录（覆盖 vault 路径） | `{vault_path}/我的作品` |
| `BLOG_NAME` | 公众号名称（文章底部显示） | 空 |
| `WECHAT_COVER_IMAGE` | 默认封面图路径 | 自动检测 |
| `WECHAT_TYPESET_DIR` | wechat-typeset-pro skill 路径 | `./skills/wechat-typeset-pro` |
| `WECHAT_APP_ID` | 微信公众号 AppID | 空 |
| `WECHAT_APP_SECRET` | 微信公众号 AppSecret | 空 |
| `WECHAT_AUTHOR` | 公众号作者名 | 空 |

### 关键路径说明

本平台设计为便携式，所有路径均可通过环境变量配置：

- **数据库**默认存储在项目根目录的 `data/` 文件夹下
- **排版 skill**默认在 `skills/wechat-typeset-pro/` 下
- **排版输出**默认在项目根目录 `output/` 文件夹下
- **文章存档**默认到 Obsidian vault 的「我的作品」文件夹，可通过 `ARCHIVE_OUTPUT_DIR` 自由指定

## 微信公众号排版命令

排版功能由 `skills/wechat-typeset-pro/` 提供，支持 30 套精美主题。

### Markdown → 排版 → 预览

```bash
cd skills/wechat-typeset-pro
python3 scripts/format.py --input 文章.md --theme elegant
```

### 推送到公众号草稿箱

```bash
python3 scripts/publish.py --dir 输出目录/ --cover 封面图.jpg
```

### 一步到位（排版 + 推送）

```bash
python3 scripts/publish.py --input 文章.md --theme elegant --cover 封面图.jpg
```

### 配置微信凭证

在 Web 界面的「设置」页面中配置 AppID 和 AppSecret，或通过 `.env` 文件：

```
WECHAT_APP_ID=你的AppID
WECHAT_APP_SECRET=你的AppSecret
WECHAT_AUTHOR=作者名
```

## 内置写作风格

系统支持多种写作风格，每个风格通过外部 prompt 文件定义：

- **卡兹克（公众号长文）** — 温暖有说服力的长文，分节论述，适合 AI 科普/产品体验/方法论分享
- **日常** — 自言自语式的日常随笔，短句自嘲，自由跳跃
- **短科普** — 客观亲切的短科普，一篇讲清楚一个东西
- **小红书** — emoji 点缀的短笔记，钩子开头 + 标签结尾

你可以创建自己的 prompt 文件，也可以通过「风格自学习」功能从参考文章自动生成。

## 隐私与分发

- 本项目默认使用本地 SQLite 数据库，素材、文章和历史记录不会自动上传到第三方服务器。
- 打包目录会排除个人数据、草稿、私有配置、数据库、`.DS_Store` 和缓存文件。
- 微信公众号凭证应通过设置页或 `.env` 配置，不要写进测试文件、README 或打包产物。
- 如果曾经把 AppSecret 放进截图、测试文件或公开仓库，请到公众号后台重置。

## 技术栈

- **Python 3.10+**
- **Flask** — Web 界面
- **SQLite** — 本地数据存储
- **Claude Code CLI** — AI 写作引擎（需另行安装）
- **Markdown** — 排版引擎依赖
- **Requests** — 微信 API 调用

## 当前边界

- 这是个人写作工作流工具，不是多人协作平台。
- 公众号推送依赖微信后台配置和 IP 白名单。
- 图片和文字交错写作仍需要继续优化，复杂 Obsidian 粘贴内容可能需要手动检查。
- 生成质量高度依赖风格 prompt 和输入素材，建议先用自己的作品调好风格，再用于正式写作。

## 许可

仅供个人学习和使用。
"""
    with open(os.path.join(OUTPUT_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)
    print("  [write] README.md")


def write_requirements():
    """Write combined requirements.txt."""
    req = """# Personal Writing Platform
flask>=3.0

# WeChat Typeset Skill
markdown>=3.0
requests>=2.0
python-dotenv>=1.0
"""
    with open(os.path.join(OUTPUT_DIR, "requirements.txt"), "w") as f:
        f.write(req)
    print("  [write] requirements.txt")


def main():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
        print(f"Removed existing {OUTPUT_DIR}")

    print("Copying source code...")
    copy_source()

    print("Patching built-in styles to use external prompts...")
    patch_style_methods_to_external_prompts()
    patch_sherry()

    print("Adding external prompt loader...")
    add_style_engine_loader()

    print("Patching database path to be portable...")
    patch_db_path()

    print("Patching skill paths to be relative...")
    patch_skill_paths()

    print("Patching personal paths to be configurable...")
    patch_obsidian_bridge()
    patch_wechat_footer()
    patch_cover_image()

    print("Copying misc files...")
    copy_misc()

    print("Copying wechat-typeset-pro skill...")
    copy_wechat_skill()

    print("Writing README.md and requirements.txt...")
    write_readme()
    write_requirements()

    # Count
    total = 0
    for root, dirs, files in os.walk(OUTPUT_DIR):
        total += len(files)
    print(f"\nDone. {total} files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
