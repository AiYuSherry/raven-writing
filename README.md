# 乌鸦写作台

[更新记录](#更新记录) | [项目介绍](#中文) | [English](#english)

## 更新记录

### 2026-05-06

- **标题工坊改为标签切换模式**：「标题生成」和「标题积累」拆分为两个标签按钮，点击切换显示对应内容，两个标签始终可见，便于快速跳转。
- **生成记录归入标题生成标签**：生成记录从标题积累区域移回标题生成标签下，功能归属更清晰。
- **标签按钮文字跟随主题色**：文字颜色使用 `var(--ink)`，白模式黑色、黑模式白色，底部阴影线区分激活状态。
- **20 字硬约束**：AI 生成的标题候选强制控制在 20 字以内，超出自动丢弃，最多保留 10 个候选。
- **自定义撰写**：标题候选区支持手动撰写标题并直接添加到积累库。
- **重新生成**：不满意 AI 结果可一键重新生成，无需刷新页面。
- **清空素材**：素材区增加清空按钮，快速清除旧内容。
- **生成记录查看素材**：每条生成记录可展开查看当时使用的完整素材内容。

### 2026-05-05 正式发布项目

- 本地优先的 AI 写作工作台，支持素材导入、多风格文章生成、标题工坊、文章反复修改、Obsidian 存档、微信公众号排版与推送。
- 内置四种写作风格：卡兹克公众号长文、日常随笔、短科普、小红书笔记。
- 纯本地运行，数据存储在 SQLite 中，支持通过上传作品或 SKILL.md 自定义风格。

## 中文

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

---

## English

Raven Writing Desk is a local-first AI writing workspace for automated, personalized writing workflows. It brings material intake, style generation, article revision, headline analysis, Obsidian archiving, WeChat article typesetting, and draft publishing into one focused interface.

It is not a general chat box. It is designed around a repeatable writing pipeline: collect material, choose a style, generate a draft, refine the article, pick or improve headlines, archive the final version, and publish when ready.

## Core Features

### Writing Workspace

- Paste text, upload files, and import writing materials.
- Generate multiple article versions with different writing styles.
- See the style attached to each generated article, then revise and archive each version independently.
- Continue revising articles while keeping the edit request and detected changes visible.
- Apply hard constraints to reduce AI-flavored phrasing, banned sentence patterns, and cross-style leakage.

### Style System

- Includes four built-in styles: Khazix long-form WeChat articles, Daily Notes, Short Explainers, and Xiaohongshu Notes.
- Create custom styles from your own writing samples, reference files, or SKILL.md files.
- Edit prompts, reference materials, and style descriptions in the web UI.
- The Khazix display style keeps the internal `sherry` style id for compatibility and still runs through the Sherry skill path.

### Headline Workshop

- Generate multiple headline candidates for each article.
- Save good headlines you encounter in daily reading and organize them by category.
- Add headlines one by one or in batches.
- Periodically ask AI to analyze the headline library, extract reusable patterns, and add strong patterns to the headline formula library.
- Future headline generation can then draw from these formulas, making candidates closer to your taste and platform needs.

### Review, Archive, and Stats

- Keep history for materials, sessions, article versions, and revisions.
- Archive final Markdown versions to Obsidian or any configured folder.
- Preserve draft/final differences for later review and prompt improvement.
- Track writing counts and style distribution.

### WeChat Typesetting and Publishing

- Bundles the `wechat-typeset-pro` skill.
- Converts Markdown into WeChat-compatible HTML.
- Provides multi-theme previews.
- Can push selected results to the WeChat Official Account draft box after credentials are configured.

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
# or
pip install -e .
```

### 2. Install Claude Code

Raven Writing Desk uses Claude Code CLI as the default writing engine.

```bash
npm install -g @anthropic-ai/claude-code
```

### 3. Start the Web App

```bash
python -m personal_writing.web.app
# or
personal-writing web
```

Open `http://localhost:5000` in your browser.

## Built-In Prompts

| File | Style | Included |
|------|-------|----------|
| `prompts/sherry.md` | Khazix long-form WeChat articles | Yes |
| `prompts/daily.md` | Daily Notes | Yes |
| `prompts/short_science.md` | Short Explainers | Yes |
| `prompts/xiaohongshu.md` | Xiaohongshu Notes | Yes |

You can create more custom styles from the web UI by uploading SKILL.md files, reference articles, or manually writing prompts.

## Common Workflows

### From Material to Article

1. Paste text or upload files in the writing workspace.
2. Select one or more writing styles.
3. Generate drafts and revise each style-specific result independently.
4. Pick a generated headline or write your own.
5. Export Markdown or archive the final version to Obsidian.

### From Good Headlines to Better Headline Generation

1. Save strong headlines you encounter into the Headline Workshop.
2. Tag them by theme, platform, or content type.
3. Periodically ask AI to summarize headline patterns.
4. Add effective patterns to the formula library.
5. Use the accumulated formulas to improve future headline candidates.

### From Article to WeChat Draft

1. Generate or paste a Markdown article.
2. Preview it with the built-in WeChat typesetting themes.
3. Configure WeChat credentials in Settings or environment variables.
4. Push the formatted article to the WeChat draft box.

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `WRITING_STYLES_DIR` | Prompt directory | `./prompts/` |
| `PERSONAL_WRITING_ROOT` | Project root override | Auto-detected |
| `PERSONAL_WRITING_DATA` | Database directory | `{project_root}/data` |
| `OBSIDIAN_VAULT_PATH` | Obsidian vault path | Auto-detected |
| `ARCHIVE_OUTPUT_DIR` | Archive output directory | `{vault_path}/我的作品` |
| `BLOG_NAME` | WeChat footer account name | Empty |
| `WECHAT_COVER_IMAGE` | Default WeChat cover image | Auto-detected |
| `WECHAT_TYPESET_DIR` | WeChat typeset skill path | `./skills/wechat-typeset-pro` |
| `WECHAT_APP_ID` | WeChat Official Account AppID | Empty |
| `WECHAT_APP_SECRET` | WeChat Official Account AppSecret | Empty |
| `WECHAT_AUTHOR` | WeChat author name | Empty |

## Privacy and Distribution

- The app uses a local SQLite database by default.
- Materials, drafts, and history are not uploaded to third-party servers by the app itself.
- Packaged releases exclude personal data, drafts, private config, databases, `.DS_Store`, and cache files.
- WeChat credentials should be configured through Settings or `.env`, never committed to the repository.

## Tech Stack

- Python 3.10+
- Flask
- SQLite
- Claude Code CLI
- Markdown
- Requests

## 许可

仅供个人学习和使用。
