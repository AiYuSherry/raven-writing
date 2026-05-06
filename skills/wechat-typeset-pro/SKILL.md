# wechat-typeset-pro

微信公众号专业排版技能。把 Markdown 文章转为微信公众号兼容的精美内联样式 HTML，30 套主题 + 可视化画廊选择 + 轻量结构整理 + 一键复制到公众号。可选推送到草稿箱。

## Skill Description

微信公众号专业排版引擎：Markdown → 精美微信兼容 HTML。当用户说"排版""微信排版""公众号排版""format""美化文章"时使用。支持 30 套精美主题、可视化画廊预览、轻量结构整理、深色模式、代码高亮。

## When to Use

- 用户需要将 Markdown 文章排版为微信公众号格式
- 用户说"排版"时调用
- `wechat-content-studio` 技能的排版流程调用本技能
- 需要预览多种主题风格并选择最佳方案

## 脚本目录

`{baseDir}` = 本 SKILL.md 所在目录。

| 脚本                   | 用途                                |
| ---------------------- | ----------------------------------- |
| `scripts/format.py`  | 排版引擎：Markdown → 微信兼容 HTML |
| `scripts/publish.py` | 推送：HTML → 公众号草稿箱          |

## 配置

配置文件：`{baseDir}/config.json`

微信凭证优先从环境变量读取（`.env`），无需在 config.json 中配置敏感信息。

### 环境变量（自动从 .env 加载）

| 变量                  | 用途                 |
| --------------------- | -------------------- |
| `WECHAT_APP_ID`     | 微信公众号 AppID     |
| `WECHAT_APP_SECRET` | 微信公众号 AppSecret |

## Instructions

### 检查点协议（多步流程通用）

排版属于多步工作流，必须按检查点节奏推进：

1. 每完成一个主要步骤（确认文章 / 结构化预处理 / 轻量整理 / 主题选择 / 排版生成 / 推送草稿箱），**先写入检查点再向用户汇报**：

   ```
   ✅ 已完成：<step>
   ⏭ 下一步：<next>
   请回复：继续 / 修改 / 停止
   ```

2. 检查点文件：`~/.claude/state/wechat-typeset-pro-checkpoint.json`（目录缺失先 `mkdir -p`），字段：

   ```json
   {
     "skill": "wechat-typeset-pro",
     "started_at": "ISO 时间戳",
     "input": "源 .md 或 .docx 路径",
     "last_step": "confirm | structure | enhance | theme | format | publish",
     "next_step": "...",
     "context": { "title": "", "theme": "", "draft_url": "" },
     "status": "in_progress | paused | completed"
   }
   ```

3. **中断恢复**：进入本 skill 前先 `Read` 检查点文件。若存在 `status=paused`，告知用户上次进度并询问继续 / 重做 / 放弃，**绝不从头跑**。
4. 收到 `[Request interrupted by user]` 或用户「算了 / 停」立即保存检查点并停手。
5. 用户「默认工作流」(只说"排版")的场景仍然适用：每个主步骤后简短报告即可，不需要每步等确认；但**主题选择**和**推送草稿箱**两个节点必须停下等回复。

### 默认工作流（用户说"排版"时）

用户仅说"排版这篇文章"时，执行以下默认流程，**不再询问**确认：

1. **提取标题**：从 Word 文档（`.docx`）中提取文章标题
2. **排版**：用推荐主题执行 Markdown → 微信兼容 HTML 排版
3. **推送草稿箱**：自动调用 `publish.py` 推送到公众号草稿箱
4. **固定作者**：`--author "流深 Sherry"`
5. **默认封面**：如用户未指定封面图，使用 `~/path/to/your/cover-image.png`
6. **固定尾部**：确认文章末尾有灰色斜体提示；如原文没有，则追加固定尾部，并居中对齐。同时横线与正文区分。

完整命令示例：

```bash
python3 {baseDir}/scripts/publish.py \
  --input "文章.md" \
  --theme terracotta \
  --title "从Word提取的标题" \
  --author "流深 Sherry" \
  --cover "~/path/to/your/cover-image.png"
```

如果用户明确说"只排版，不推送"，则跳过推送步骤。

### 完整工作流

#### 第 1 步：确认文章

1. 如果用户给了文件路径，直接读取
2. 如果没给路径，问用户要文章路径
3. **优先使用用户修改后的 Word 文档**：如果用户声明"改完了""根据我改完的 Word 排版"或类似表达，表明之前生成的 Word 文档已被用户手动修改过，则排版时必须以用户修改后的 `.docx` 文件内容为准，重新提取文本进行排版，而不是使用原始 Markdown 文件
4. 读取文章内容，确认标题和字数

#### 第 1.5 步：结构化预处理（仅在需要时）

读取文章后，检测 Markdown 结构完整度。

**判断规则**：

- 有 `##` 标题且格式标记分布合理 → 跳过，直接进入第 2 步
- 缺少 `##` 标题或几乎没有格式标记 → 执行结构化

**结构化规则（只加标记，不改内容）**：

1. 识别逻辑段落插入 `##` 标题（从内容提炼，不编造）
2. 确保段落之间有空行分隔
3. 识别并列内容加列表标记
4. 识别关键词加 `**加粗**`
5. 清理格式（多余空行、缩进、标点）
6. **不改措辞**：不调语序、不增删内容

保存为 `~/output/wechat-typeset-pro/xxx-structured.md`（与 `config.json` 的 `output_dir`，即 `path.join(HOME, 'output', 'wechat-typeset-pro')` 一致），告知用户。

#### 第 2 步：轻量内容整理 + 自动套格式

默认目标是**像人工认真排过的公众号**，而不是“信息卡片化”或“花哨网页化”。

只做轻量、克制的 Markdown 整理：

1. **保留原标题与原段落逻辑**，不擅自改写论点
2. **必要时补充 `##` 标题**，但仅限原文已经存在明显段落层次
3. **分隔符** → 章节转换处可酌情补 `---`
4. **图说** → 图片后斜体：`*图片说明*`
5. **列表化** → 仅当原文本身就是并列项时再转列表
6. **固定尾部** → 如果文章末尾没有固定提示，追加以下灰色斜体内容：

```markdown
<font color="#808080"><i>感谢阅读。如果对你有帮助，欢迎点赞收藏转发。</i></font>
<font color="#808080"><i>关注公众号律海流深，获取更多 AI 实操经验。</i></font>
```

默认**不要主动添加**以下内容，除非用户明确要求或原文已经提供相应结构：

- `> [!important]` / `> [!tip]` / `> [!warning]` 这类 callout 色块
- “核心观点”“一句话总结”“阅读提示”之类编辑性总结框
- `:::dialogue` / `:::gallery` / `:::timeline` / `:::compare` 等容器
- 为了“更好看”而额外生成的小结、提炼、金句卡片

优先保留文章本身的呼吸感、留白和正常段落推进。

保存增强后 Markdown 为 `~/output/wechat-typeset-pro/xxx-enhanced.md`。

#### 第 2.5 步：推荐主题

根据内容分析推荐 3 个最适合的主题。对中文长文，优先推荐克制、低装饰的主题：

| 内容类型        | 推荐主题                                 |
| --------------- | ---------------------------------------- |
| 深度长文/分析   | newspaper, magazine, ink                 |
| 科技产品/AI工具 | bytedance, github, sspai                 |
| 访谈/对话体     | terracotta, coffee-house, mint-fresh     |
| 教程/操作指南   | github, sspai, bytedance                 |
| 文艺/随笔/观点  | terracotta, sunset-amber, lavender-dream |
| 活力/动态/速报  | sports, bauhaus, chinese                 |

#### 第 3 步：打开主题画廊（默认）

```bash
python3 {baseDir}/scripts/format.py \
  --input "文章路径.md" \
  --gallery \
  --recommend newspaper magazine ink
```

用**真实文章**渲染 20 个主题，浏览器中选择。

#### 第 3 步（备选）：直接指定主题

```bash
python3 {baseDir}/scripts/format.py \
  --input "文章路径.md" \
  --theme terracotta
```

#### 第 4 步：确认结果

- Gallery 模式：浏览器中切换主题，选中后点按钮复制，粘贴到公众号后台
- 直接模式：浏览器中检查预览，点「复制到微信」

### 推送到草稿箱（可选）

用户说"推送""发公众号"时执行：

```bash
python3 {baseDir}/scripts/publish.py \
  --dir "排版输出目录" \
  --cover "封面图路径（可选）"
```

如果用户没有指定封面图，`--cover` 默认填写：

```bash
~/path/to/your/cover-image.png
```

从 Markdown 直接推送：

```bash
python3 {baseDir}/scripts/publish.py \
  --input "文章.md" \
  --theme terracotta
```

### 参数说明

**format.py**：

- `--input` / `-i`：Markdown 文件路径（必须）
- `--gallery`：打开主题画廊（推荐）
- `--theme` / `-t`：直接指定主题名
- `--output` / `-o`：输出目录（默认 `~/output/wechat-typeset-pro`，即 `path.join(HOME, 'output', 'wechat-typeset-pro')`）
- `--recommend`：推荐主题 ID 列表
- `--no-open`：不自动打开浏览器
- `--format`：输出格式 wechat/html/plain

**publish.py**：

- `--dir`：排版输出目录
- `--input`：Markdown 文件路径（自动排版再推送）
- `--cover` / `-c`：封面图路径
- `--title` / `-t`：文章标题
- `--theme`：排版主题（仅 --input 模式有效）
- `--author` / `-a`：作者名
- `--dry-run`：只做排版，不推送

## 可用主题（30 个）

### 独立风格（9 个）

| 主题   | ID             | 风格                   |
| ------ | -------------- | ---------------------- |
| 赤陶   | `terracotta` | 暖橙色，满底圆角标题   |
| 字节蓝 | `bytedance`  | 蓝青渐变，科技现代     |
| 中国风 | `chinese`    | 朱砂红，古典雅致       |
| 报纸   | `newspaper`  | 纽约时报风，严肃深度   |
| GitHub | `github`     | 开发者风，浅色代码块   |
| 少数派 | `sspai`      | 中文科技媒体红         |
| 包豪斯 | `bauhaus`    | 红蓝黄三原色，先锋几何 |
| 墨韵   | `ink`        | 纯黑水墨，极简留白     |
| 暗夜   | `midnight`   | 深色底+霓虹色          |

### 精选风格（7 个）

| 主题     | ID                 | 风格               |
| -------- | ------------------ | ------------------ |
| 运动     | `sports`         | 渐变色带，活力动感 |
| 薄荷     | `mint-fresh`     | 薄荷绿，清爽       |
| 日落     | `sunset-amber`   | 琥珀暖调           |
| 薰衣草   | `lavender-dream` | 紫色梦幻           |
| 咖啡     | `coffee-house`   | 棕色暖调           |
| 微信原生 | `wechat-native`  | 微信绿             |
| 杂志     | `magazine`       | 超大留白，品质长文 |

### 模板系列（14 个）

4 种布局（Minimal / Focus / Elegant / Bold）× 多种配色（Gold / Blue / Red / Green / Navy / Gray）

## 内置排版增强

- **CJK 间距修复**：中英文/中数字之间自动加空格
- **加粗标点修复**：`**文字，**` → `**文字**，`
- **纯内联样式**：所有 CSS 写在 `style="..."` 上
- **列表模拟**：`<ul>/<ol>` → `<section>` + flexbox
- **外链转脚注**：自动变为正文标注 + 文末脚注
- **语法高亮**：代码块自动着色 + Mac 风格工具栏
- **深色模式**：自动生成微信深色模式 data-darkmode-* 属性
- **多类型 callout**：tip/note/important/warning/caution 各有独立配色
  仅在原文显式使用 callout 语法或用户明确要求强调卡片时启用；默认不主动添加
- **图说识别**：图片后斜体自动变居中灰色图说
- **对话气泡**：`:::dialogue` 左右交替聊天气泡
- **图片画廊**：`:::gallery` 横向滚动多图容器
- **时间线**：`:::timeline` 时间线展示
- **步骤流程**：`:::steps` 编号步骤
- **对比卡片**：`:::compare[A vs B]` 两列对比
- **人物引言**：`:::quote[人名]` 引言卡片
- **表格斑马纹**：自动奇偶行背景色

## 高级容器语法（按需使用，默认不用）

以下语法只在用户明确想要更强视觉表现，或原文天然适配时使用。普通公众号长文、散文、观点文、经验文默认不要主动插入。

```markdown
## 第一部分

这里是正文段落。保持正常的公众号阅读节奏，不额外插入总结框。

---

## 第二部分

- 只有原文本身是并列项时，才转成列表
- 图片后如需说明，可保留简洁图说

*图片说明*
```

---

## 复盘记录（教训与规范）

### 1. Markdown 标题层级必须严格使用 #/##/###

**问题：** 如果文章用 `**粗体**` 代替 `##` 作为标题，format.py 无法识别标题层级，导致所有文字变成同一大小的正文，完全丧失层级区分。

**正确做法：**

- 文章主标题用 `#`
- 一级大标题（如"一、项目缘起"）用 `##`
- 二级小标题（如"1. 自动爬取新歌"）用 `###`
- 绝对不能用 `**粗体**` 代替标题语法

### 2. 推送草稿箱时封面图处理

**问题：** 微信 API 强制要求封面图，没有封面图推送会直接报错。

**正确做法：**

- 如果用户明确提供了封面图路径，用用户指定的
- 如果用户未指定封面图，默认用 `~/path/to/your/cover-image.png`
- 不要尝试用 canvas-design 等复杂流程实时生成封面图，直接使用默认封面素材即可
