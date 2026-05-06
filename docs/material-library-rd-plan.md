# 乌鸦写作台素材库研发计划

## 1. 当前项目判断

### 技术栈

- Web：Flask，入口在 `src/personal_writing/web/app.py`，模板在 `src/personal_writing/web/templates/`。
- 数据库：SQLite，本地库文件 `data/personal_writing.db`，schema 在 `src/personal_writing/db/schema.py`。
- 数据访问：轻量 Repository 模式，集中在 `src/personal_writing/db/repository.py`。
- 写作引擎：`src/personal_writing/core/pipeline.py` 负责读取输入、落库、调用模型、保存文章。
- 模型调用：`src/personal_writing/utils/claude_client.py` 通过本机 Claude Code CLI 子进程调用模型。
- 输入读取：`src/personal_writing/core/input_reader.py` 目前支持纯文本、URL 字符串、目录、文本类文件、Excel/CSV；PDF/Word 还没有正式解析。
- 风格系统：`src/personal_writing/core/style_engine.py` + `src/personal_writing/styles/`，已有 Sherry、日常、短科普、小红书、郑戈论文风格。
- UI 设计：项目根目录已有 `DESIGN.md`，当前 `base.html` 采用侧边栏工作台、暖纸色/黑白主题、卡片式工具界面。后续素材库界面应继续沿用这一套，不做营销页。
- 测试：当前只有 `tests/test_nuwa_and_academic_styles.py`，覆盖女娲 skill 解析和郑戈风格元数据，尚无检索、解析、引用相关测试。

### 当前写作流程

1. 用户在 `/` 写作页粘贴内容、上传文件或输入本地路径。
2. `web/app.py` 将文件内容合并为一个大文本，调用 `pipeline.write(...)`。
3. `pipeline.write(...)` 调用 `input_reader.read_input(...)`，把输入保存到现有 `materials` 表。
4. 创建 `sessions`，逐个风格调用 `generate_one(...)`。
5. `generate_one(...)` 把完整素材拼进 prompt 的 `## 素材内容`，调用 Claude Code CLI。
6. 结果保存到 `articles`，同时保存到本地 `草稿/`。

### 当前“素材库”的真实状态

项目已有 `/materials` 页面和 `materials` 表，但它更像“写作输入历史”：

- 只有 `raw_content` 全文和简单 `source_type/status`。
- 搜索是 `LIKE`，没有全文索引、切片、embedding、重排。
- 没有库、文档、页码、段落坐标、引用片段、生成证据快照。
- 写作时不能选择某个素材库，也不能把检索结果作为受控上下文注入。
- PDF/Word/网页上传后无法稳定转为可引用的结构化来源。

因此新需求不应只是扩展旧 `materials` 表，而应新增一个论文写作专用的“素材库/知识库”层，并让写作 pipeline 通过 retrieval hook 调用它。

## 2. 产品目标和边界

### 产品目标

新增一个类似 IMA / NotebookLM 的本地素材库，但服务对象不是通用问答，而是乌鸦写作台的论文写作：

- 素材库是论文生成时的检索、索引、论证、引用和材料来源。
- 写作时模型不能只看到一个“附件文本”，而应看到经过检索、重排、压缩、带出处的证据包。
- 草稿中要能保留出处标记，支持用户回看原 PDF 页码、网页 URL、Word 段落或 Markdown 位置。
- 与现有风格系统衔接，尤其要优先服务 `zheng_ge_academic` 论文风格。

### 产品边界

- 默认本机运行，资料不主动上传云端。
- 不做多人协作、不做云盘同步、不做公开分享。
- 不承诺自动完成真实学术数据库检索。外部文献下载、知网/Westlaw 等应作为用户输入材料或后续可选连接器。
- 不让模型编造来源。素材库没有的内容必须标注“需补证”或返回缺证提示。
- 不替代 Zotero/EndNote 的完整文献管理，但要保留 DOI、作者、年份、页码等字段，便于以后对接。

## 3. 目标用户流程

### 创建素材库

1. 用户进入“素材库”页面。
2. 点击“新建素材库”，填写名称、论文主题、研究领域、默认引用格式、是否严格仅基于库内材料。
3. 系统创建 library，进入素材库详情页。

### 上传和导入材料

支持入口：

- PDF：论文、报告、判决书、法规汇编。
- Word：`.docx` 论文草稿、读书笔记。
- Markdown / TXT：用户笔记、摘录、Obsidian 导出。
- 网页 URL：政策页面、公开文章、新闻、期刊网页。
- 纯文本粘贴：临时材料、访谈摘录。

上传后流程：

1. 文件保存到本地 `data/material_library/files/`。
2. 创建 `library_documents` 记录，状态为 `queued`。
3. 后台或短任务执行解析：抽取文本、页码、标题、作者、年份、URL、文件 hash。
4. 生成 `document_chunks`，建立 FTS5 关键词索引。
5. 生成 embedding，写入 `chunk_embeddings`。
6. 状态变为 `ready`；失败则保留文件和错误信息，允许重试或手动粘贴文本。

### 查看解析结果

素材库详情页至少显示：

- 文档列表：文件名、类型、页数/字数、解析状态、上传时间。
- 文档详情：元数据、抽取文本预览、页码/段落切片、解析错误。
- 检索测试：输入一个论文问题，查看关键词结果、向量结果、混合结果和引用片段。

### 写作时选择素材库

在现有写作页 `/` 增加“论文素材库”选择区：

- 可选择一个或多个素材库。
- 可选模式：`仅基于素材库`、`素材库优先，允许常识补充`、`只检索不生成引用`。
- 可设置检索问题：默认用用户写作要求 + 论文风格 + 提纲标题自动生成，也允许用户手动输入。

### 生成时引用来源

写作生成前：

1. 根据用户输入、风格、标题/提纲生成 retrieval query。
2. 对选中的素材库做混合检索。
3. 重排后得到 evidence pack。
4. 把 evidence pack 注入 prompt，要求模型按证据编号引用。

生成后：

- 草稿正文保留引用标记，如 `[S12]` 或脚注形式。
- 文章详情页显示“引用来源面板”：每个引用对应文档、页码、原文片段、相关度。
- 保存一份 `generation_retrieval_snapshots`，保证之后即使素材库更新，也能复盘当时模型看到的证据。

## 4. 技术架构

### NotebookLM-style 索引层

#### 索引优势

NotebookLM 给人的核心优势不是“资料堆得多”，而是每个 source 都被明确纳入 notebook 的可检索范围：用户能看到系统正在基于哪些 sources 回答、每个 source 的摘要/入口，以及回答中的片段出处。乌鸦写作台不照搬品牌形态，但应吸收这三点：

- source 可见：导入后立即给出文档索引卡，让用户知道资料是否解析成功、能被切成多少片段、在哪个文件夹。
- notebook 可见：素材库详情页提供索引总览，让用户知道当前写作模型可检索的资料总量、分类覆盖和最近索引时间。
- citation 可追溯：检索结果和写作证据包都保留 `document_id`、`chunk_id`、文件夹、标题和原文片段，避免 `[S1]` 只成为不可复盘的装饰。

#### 当前 MVP

本阶段采用 deterministic/extractive 索引，不调用外部模型，降低隐私和成本风险：

- `material_library/indexing.py` 提供 `build_source_guide(...)` 和 `build_library_index_summary(...)`。
- 文档索引卡从抽取文本和 chunks 中生成：自动摘要、关键词/术语、建议追问、字数、页数、chunk 数、文件夹和解析状态。
- 素材库详情页展示索引总览：文档数、chunk 数、文件夹数、可检索文档数、最近索引时间、按文件夹的文档/切片数量。
- 检索结果继续支持全库检索与文件夹范围检索，并在页面上展示 `document_id`、`chunk_id`、分类、来源标题和 excerpt。
- 写作页选择文件夹范围时，证据包会写明检索范围；生成结果下方的引用来源面板显示可回溯来源。

#### 后续增强

- Embedding：在现有 FTS/LIKE 检索外增加本地 embedding，形成关键词 + 语义混合检索；远程 embedding 只能作为显式设置项。
- OCR：为扫描 PDF 增加 `ocrmypdf` / `tesseract` 降级链路，并在 source guide 中标明 OCR 置信度和失败原因。
- Source discovery：先做本地流程设计，用户输入论文题目/关键词后，系统从本地文件夹、Obsidian、历史素材、浏览器保存网页或用户配置目录中提出候选资料源；用户确认后再加入素材库。外网学术搜索、网页发现和下载连接器作为后续可选扩展，不在 MVP 自动联网。
- Citation audit：生成后检查正文 `[Sx]` 是否存在于 snapshot，进一步检查引用句和 source excerpt 的关键词重合、页码/文档是否匹配，输出缺证报告。

### 模块划分

建议新增 `src/personal_writing/material_library/`：

- `storage.py`：本地文件落盘、hash、路径管理、删除保护。
- `extractors.py`：PDF/Word/Markdown/HTML/文本解析。
- `chunker.py`：按页、标题、段落和 token 长度切片。
- `embeddings.py`：本地 embedding provider，可选远程 provider。
- `retrieval.py`：关键词检索、向量检索、混合检索。
- `reranker.py`：轻量重排，MVP 可先用规则分数，后续加本地 cross-encoder。
- `context_builder.py`：把检索结果组装为模型上下文。
- `citation.py`：引用编号、出处格式、引用覆盖检查。
- `jobs.py`：解析/索引任务状态机。

### 文件存储

默认路径：

- 原始文件：`data/material_library/files/{library_id}/{document_id}/{original_name}`
- 抽取文本：可存 DB，也可同步保存 `data/material_library/extracted/{document_id}.txt`
- 调试产物：`data/material_library/debug/{document_id}/`

文件命名使用 `document_id + safe filename`，并保存 `sha256`，避免重复导入。

### 文本抽取

优先级：

- PDF：
  - 首选 `PyMuPDF`（`pymupdf`）：速度快，可保留页码和块坐标。
  - 降级 `pypdf`：纯文本抽取。
  - 再降级 `pdftotext` 命令行，如果本机可用。
  - 扫描 PDF 暂不在 MVP 做 OCR；增强版可接 `ocrmypdf`/`tesseract`。
- Word：
  - `.docx` 用 `python-docx` 抽段落、标题、表格。
  - `.doc` 不直接承诺，优先提示用户转 `.docx`；增强版可尝试 `textutil` 或 LibreOffice headless。
- 网页：
  - 首选 `trafilatura` 抽正文、标题、作者、发布日期。
  - 降级 `readability-lxml` + `BeautifulSoup`。
  - 最后保存 HTML 文本清洗结果，并标注低置信度。
- Markdown/TXT：
  - 直接读取，Markdown 保留标题层级。
- HTML 本地文件：
  - 用 `BeautifulSoup` 清理脚本、样式后抽正文。

### 切片策略

切片原则：

- PDF 默认以页为硬边界，页内按段落合并到 500-900 中文字符左右。
- Word/Markdown 优先按标题层级，再按段落和长度切片。
- 网页按正文段落和小标题切片。
- 每个 chunk 保存 `document_id/page_start/page_end/section_title/char_start/char_end/text`。
- chunk 之间允许 80-120 字 overlap，避免论证链断裂。
- 对法规、判决、论文脚注可后续增加专门切片器。

### Embedding

本地优先：

- MVP 可先接 `sentence-transformers` 的轻量多语模型，如 `BAAI/bge-small-zh-v1.5` 或同类本地模型。
- embedding 向量以 float32 BLOB 或 JSON 存 SQLite。
- 小规模本地库可以先在 Python 中加载候选向量并做 cosine，相比引入复杂向量库更容易落地。

增强版：

- 接 `sqlite-vec` 或 `faiss-cpu` 做向量索引。
- 可选远程 embedding provider，例如 OpenAI embeddings，但必须在设置中显式开启，并提示材料会发送到远程服务。

### 关键词检索

- 用 SQLite FTS5 建 `document_chunks_fts`。
- 中文分词在 SQLite 默认 tokenizer 下有限，但对论文关键词、英文、法条编号、专名仍有价值。
- 可增加一列 `keywords`，用规则抽取标题、作者、年份、法条号、专名、用户标签。

### 混合检索与重排

检索流程：

1. Query rewrite：根据用户写作任务生成 2-4 个检索问题，例如“概念定义”“支持论据”“反方观点”“规范依据”。
2. FTS5 取 top 30。
3. Vector 取 top 30。
4. 合并去重，按 `0.45 * vector + 0.35 * keyword + 0.20 * metadata_boost` 初排。
5. 重排：
   - MVP：标题命中、页码邻近、文档可信度、最近上传、用户 pin 的材料加权。
   - 增强版：本地 cross-encoder reranker。
6. 上下文组装：选 top 8-15 个 chunk，按论证主题分组，限制总字数。

### 上下文组装

`context_builder.py` 生成结构化 evidence pack：

```text
## 素材库证据包
检索范围：素材库 A、素材库 B
生成规则：只能使用以下证据支持事实判断；没有证据时写“需补证”。

[S1] 文档：《xxx》 作者 年份 p.12
原文片段：...
可用方式：概念定义 / 支持论据 / 反方观点

[S2] ...
```

模型 prompt 要求：

- 每个事实性断言尽量挂接 `[Sx]`。
- 不得引用 evidence pack 之外的具体文献、页码、案例、数据。
- 不能确定出处时写“需补证”。
- 文末输出“引用来源”列表，或在正文中保留脚注标记。

## 5. 数据模型

现有 `materials` 表继续保留为“单次写作输入历史”。新增论文素材库表，不直接重命名旧表，降低破坏性。

### 新增表

#### `material_libraries`

- `id INTEGER PRIMARY KEY`
- `name TEXT NOT NULL`
- `description TEXT DEFAULT ''`
- `topic TEXT DEFAULT ''`
- `discipline TEXT DEFAULT ''`
- `citation_style TEXT DEFAULT 'inline_source_id'`
- `strict_grounding INTEGER DEFAULT 1`
- `created_at TEXT`
- `updated_at TEXT`

索引：

- `idx_material_libraries_updated_at`

#### `library_documents`

- `id INTEGER PRIMARY KEY`
- `library_id INTEGER NOT NULL`
- `title TEXT DEFAULT ''`
- `original_filename TEXT DEFAULT ''`
- `file_path TEXT DEFAULT ''`
- `source_type TEXT NOT NULL`：`pdf/docx/md/txt/html/url/paste`
- `source_url TEXT DEFAULT ''`
- `mime_type TEXT DEFAULT ''`
- `sha256 TEXT DEFAULT ''`
- `author TEXT DEFAULT ''`
- `year TEXT DEFAULT ''`
- `published_at TEXT DEFAULT ''`
- `page_count INTEGER DEFAULT 0`
- `word_count INTEGER DEFAULT 0`
- `parse_status TEXT DEFAULT 'queued'`：`queued/processing/ready/failed`
- `parse_error TEXT DEFAULT ''`
- `created_at TEXT`
- `updated_at TEXT`

索引：

- `idx_library_documents_library_id`
- `idx_library_documents_sha256`
- `idx_library_documents_status`

#### `document_chunks`

- `id INTEGER PRIMARY KEY`
- `library_id INTEGER NOT NULL`
- `document_id INTEGER NOT NULL`
- `chunk_index INTEGER NOT NULL`
- `section_title TEXT DEFAULT ''`
- `page_start INTEGER DEFAULT 0`
- `page_end INTEGER DEFAULT 0`
- `char_start INTEGER DEFAULT 0`
- `char_end INTEGER DEFAULT 0`
- `text TEXT NOT NULL`
- `token_count INTEGER DEFAULT 0`
- `metadata TEXT DEFAULT '{}'`
- `created_at TEXT`

索引：

- `idx_document_chunks_library_id`
- `idx_document_chunks_document_id`
- `idx_document_chunks_page`
- `idx_document_chunks_chunk_index`

FTS：

```sql
CREATE VIRTUAL TABLE document_chunks_fts
USING fts5(text, section_title, content='document_chunks', content_rowid='id');
```

#### `chunk_embeddings`

- `chunk_id INTEGER PRIMARY KEY`
- `provider TEXT NOT NULL`
- `model TEXT NOT NULL`
- `dim INTEGER NOT NULL`
- `vector BLOB NOT NULL`
- `created_at TEXT`

索引：

- `idx_chunk_embeddings_model`

#### `library_search_logs`

- `id INTEGER PRIMARY KEY`
- `library_ids TEXT NOT NULL`
- `query TEXT NOT NULL`
- `mode TEXT DEFAULT 'hybrid'`
- `result_chunk_ids TEXT DEFAULT '[]'`
- `created_at TEXT`

用于调试检索效果和验收。

#### `generation_retrieval_snapshots`

- `id INTEGER PRIMARY KEY`
- `session_id INTEGER NOT NULL`
- `library_ids TEXT NOT NULL`
- `query TEXT NOT NULL`
- `retrieval_policy TEXT NOT NULL`
- `evidence_json TEXT NOT NULL`
- `created_at TEXT`

#### `article_citations`

- `id INTEGER PRIMARY KEY`
- `article_id INTEGER NOT NULL`
- `snapshot_id INTEGER DEFAULT 0`
- `source_label TEXT NOT NULL`：如 `S12`
- `document_id INTEGER NOT NULL`
- `chunk_id INTEGER NOT NULL`
- `quoted_text TEXT DEFAULT ''`
- `citation_text TEXT DEFAULT ''`
- `created_at TEXT`

### 现有表建议新增字段

#### `sessions`

- `library_ids TEXT DEFAULT '[]'`
- `retrieval_policy TEXT DEFAULT '{}'`
- `retrieval_snapshot_id INTEGER DEFAULT 0`

#### `articles`

- `citation_summary TEXT DEFAULT '{}'`
- `grounding_status TEXT DEFAULT ''`：`not_checked/grounded/partial/unsupported`

这些字段可以通过 `MIGRATIONS` 增量添加，保持旧数据可用。

## 6. 后端接口

### 页面路由

- `GET /libraries`：素材库列表。
- `GET /libraries/<library_id>`：素材库详情、文档列表、检索测试。
- `GET /libraries/<library_id>/documents/<document_id>`：文档解析详情。

### API

素材库 CRUD：

- `GET /api/v1/libraries`
- `POST /api/v1/libraries`
- `GET /api/v1/libraries/<id>`
- `PATCH /api/v1/libraries/<id>`
- `DELETE /api/v1/libraries/<id>`：MVP 可先禁用或只做软归档，避免误删资料。

文档上传与解析：

- `POST /api/v1/libraries/<id>/documents`
- `GET /api/v1/libraries/<id>/documents`
- `GET /api/v1/documents/<document_id>`
- `POST /api/v1/documents/<document_id>/parse`
- `POST /api/v1/documents/<document_id>/reindex`
- `DELETE /api/v1/documents/<document_id>`：必须二次确认，优先软删除。

搜索和引用：

- `POST /api/v1/libraries/search`
  - body：`library_ids/query/mode/top_k`
  - 返回：chunk、文档、页码、分数、引用 label。
- `GET /api/v1/chunks/<chunk_id>`
- `POST /api/v1/citations/preview`

写作接入：

- `POST /api/v1/write/preview-retrieval`
  - 只检索不生成，让用户先看证据包。
- 修改现有 `/` POST 和 `pipeline.write(...)`，增加：
  - `library_ids`
  - `retrieval_policy`
  - `retrieval_query`
  - `strict_grounding`

## 7. 前端/界面计划

继续使用现有工作台设计，不做首页/营销页。

### 最少页面

#### 素材库列表页

路径：`src/personal_writing/web/templates/libraries.html`

元素：

- 新建素材库按钮。
- 素材库列表：名称、主题、文档数、ready/failed 状态、更新时间。
- 搜索/筛选：主题、状态、最近使用。

#### 素材库详情页

路径：`src/personal_writing/web/templates/library_detail.html`

元素：

- 顶部：库名、主题、严格引用开关、默认引用格式。
- 上传区：PDF/Word/Markdown/网页/文本。
- 文档表：解析状态、页数、字数、错误、重试。
- 检索测试面板：输入问题，展示命中片段和出处。
- 最近生成记录：哪些文章使用过此库。

#### 文档详情页

路径：`src/personal_writing/web/templates/library_document.html`

元素：

- 元数据编辑：标题、作者、年份、URL、标签。
- 解析结果预览：按页/标题展示 chunks。
- 失败诊断：错误信息、降级建议、重新解析按钮。

#### 写作页组件改造

在 `write.html` 的“素材”或“选择风格”之间增加“论文素材库”卡片：

- 素材库选择器。
- 检索模式选择。
- “预览证据包”按钮。
- 引用严格度开关。
- 当前证据包摘要。

#### 结果页引用面板

在生成结果的 `article-tools` 附近增加：

- 引用来源列表。
- 未支撑断言提示。
- 点击 `[Sx]` 查看原文片段。

## 8. 模型写作接入

### Retrieval hook

建议在 `pipeline.py` 中把写作链拆成：

1. `prepare_generation_context(...)`
2. `retrieve_evidence_if_needed(...)`
3. `generate_one(...)`
4. `validate_citations(...)`
5. `save_generation_outputs(...)`

MVP 可先保留 `generate_one(...)` 主体，只在进入 prompt 前插入：

```python
evidence_pack, snapshot_id = build_evidence_pack(
    library_ids=library_ids,
    user_prompt=raw_input,
    style_name=sname,
    retrieval_policy=retrieval_policy,
)
```

然后把 `evidence_pack` 加到 `write_prompt` 中。

### 严格基于素材库

Prompt 约束：

- “事实性陈述必须来自证据包，并在句末标注 `[Sx]`。”
- “证据包没有的信息，不得生成具体文献名、案例名、页码、数据。”
- “没有证据但结构上需要的位置，写 `需补证：缺少xxx材料`。”
- “可以使用写作风格模型处理结构、概念和表达，但不能把风格模型当事实来源。”

程序约束：

- 生成后扫描正文中的 `[Sx]`，检查是否存在于 snapshot。
- 对没有引用的强事实段落做提示，不强行自动改。
- 若 strict 模式下引用覆盖率太低，标记 `grounding_status='partial'`，在 UI 提醒用户。

### 避免幻觉

- evidence pack 中只给短片段和出处，不给“总结性假来源”。
- 禁止模型生成新文献条目。
- 对 `zheng_ge_academic` 风格保留现有“不得编造文献、法条、案例、页码”规则，并追加“素材库证据优先级高于作者风格规则”。
- 保存 snapshot，便于复盘。
- 论文级阶段增加“引用核查”二次模型调用或规则检查。

## 9. 本地优先、安全与隐私

### 本地优先

- SQLite 继续作为默认数据库。
- 原始文件保存在项目 `data/` 内，不上传云。
- 文本抽取、切片、FTS 检索都在本机完成。
- embedding 默认本地模型；如果本机模型不可用，允许 FTS5-only 降级。
- 远程 embedding/远程 rerank 只能作为设置页的显式可选项。

### 安全与隐私

- 上传目录必须限制在 `data/material_library/`，文件名做 safe sanitize。
- 不在日志中打印完整论文材料，只记录 document_id、chunk_id、错误摘要。
- `data/` 下的原始文件、embedding、抽取文本都应被视为敏感资料。
- 删除操作默认软删除或二次确认，避免误删论文资料。
- 远程模型调用前在 UI 提示：写作生成会把 evidence pack 片段发送给模型 CLI 对应的服务。
- API 不允许任意读取本机路径；本地路径导入应继续使用白名单/确认机制，避免路径穿越。

## 10. 测试与验收

### MVP 验收

- 能新建素材库。
- 能上传 Markdown/TXT/PDF/Docx 中至少三类材料。
- 能看到解析状态、字数、页码或段落。
- 能对一个素材库检索关键词，返回原文片段和出处。
- 写作页能选择素材库并生成带 `[Sx]` 标记的论文草稿。
- `generation_retrieval_snapshots` 能记录当次证据包。
- 旧的普通写作、不选素材库时不受影响。

测试建议：

- `tests/test_material_extractors.py`
- `tests/test_material_chunker.py`
- `tests/test_material_retrieval.py`
- `tests/test_pipeline_retrieval_hook.py`

### 增强版验收

- 混合检索比纯关键词检索更稳定，能找出同义表达。
- 支持网页 URL 正文抽取和失败降级。
- 支持检索预览证据包。
- 引用面板能从文章 `[Sx]` 跳回 chunk。
- 支持重试解析、重建索引。
- 文档详情页可编辑元数据。

### 论文级可用版验收

- 长论文任务可按章节检索不同证据包。
- 能区分概念定义、支持论据、反方观点、规范依据。
- 能生成“引用来源清单”。
- 能标注“需补证”位置。
- 能对生成草稿做 citation audit：引用是否存在、页码是否存在、片段是否支持句子。
- 对 20-50 篇论文级 PDF 的本地素材库，检索响应仍在可接受范围内。

## 11. 三阶段里程碑

### 阶段一：MVP，本地可用素材库

目标：把“普通附件”升级为“可检索、可引用的本地资料库”。

任务：

1. 新增数据库表和 Repository。
2. 新增 `material_library` 模块骨架。
3. 实现文件保存、Markdown/TXT/PDF/Docx 基础解析。
4. 实现 chunk 生成和 FTS5 搜索。
5. 写作页可选择素材库。
6. pipeline 注入 evidence pack。
7. 草稿输出 `[Sx]`，保存 retrieval snapshot。
8. 添加基础测试。

### 阶段二：增强版，混合检索和可视化引用

目标：让素材库接近 NotebookLM/IMA 的研究体验。

任务：

1. 接本地 embedding。
2. 实现向量检索 + FTS5 混合检索。
3. 增加检索预览面板。
4. 增加网页导入。
5. 增加文档详情和 chunk 详情。
6. 增加引用面板和 `[Sx]` 跳转。
7. 增加失败重试、重建索引。
8. 增加搜索日志和检索质量调试。

### 阶段三：论文级可用版，论证与引用核查

目标：让素材库成为论文草稿的证据系统，而不是资料堆。

任务：

1. Query rewrite：按“概念/规范/案例/反方/历史脉络”拆检索问题。
2. 章节级 retrieval：提纲每章单独取证据包。
3. 引用核查：检查 `[Sx]` 是否真实存在、是否支撑句子。
4. 元数据增强：作者、年份、刊物、DOI、页码、标签。
5. 引用格式导出：脚注、尾注、简易 GB/T 7714 风格。
6. 支持 OCR 降级链路。
7. 针对法学论文增加法规/案例/文献类型识别。
8. 形成“缺证报告”，告诉用户还缺哪类材料。

## 12. 建议修改文件清单

现有文件建议修改：

- `src/personal_writing/db/schema.py`
  - 新增素材库相关表、FTS5 表、session/article 字段迁移。
- `src/personal_writing/db/repository.py`
  - 新增 `MaterialLibraryRepo`、`LibraryDocumentRepo`、`DocumentChunkRepo`、`RetrievalSnapshotRepo`、`ArticleCitationRepo`。
- `src/personal_writing/web/app.py`
  - 新增素材库页面路由和 API；扩展写作 POST 参数。
- `src/personal_writing/core/pipeline.py`
  - 增加 retrieval hook、evidence pack 注入、snapshot 保存、citation validation。
- `src/personal_writing/core/input_reader.py`
  - 可复用部分读取逻辑，但 PDF/Word/网页解析建议迁入新模块，避免继续膨胀。
- `src/personal_writing/web/templates/base.html`
  - 侧边栏增加“素材库”入口；沿用现有主题变量。
- `src/personal_writing/web/templates/write.html`
  - 增加素材库选择、检索模式、证据包预览入口。
- `src/personal_writing/web/templates/materials.html`
  - 建议改名语义或文案区分“写作历史素材”和“论文素材库”，避免用户混淆。
- `src/personal_writing/web/templates/material_detail.html`
  - 同上，保留旧历史功能，不要直接替换为新素材库详情。
- `src/personal_writing/styles/zheng_ge_academic.py`
  - 加强素材库证据优先、缺证标注、引用标记格式规则。
- `requirements.txt`
  - 新增解析/检索依赖。
- `setup.py`
  - 同步新增依赖。
- `README.md`
  - 功能完成后补充素材库说明和本地隐私边界。
- `tests/test_nuwa_and_academic_styles.py`
  - 不必强改；新增独立测试文件更清晰。

## 13. 建议新增文件清单

后端：

- `src/personal_writing/material_library/__init__.py`
- `src/personal_writing/material_library/storage.py`
- `src/personal_writing/material_library/extractors.py`
- `src/personal_writing/material_library/chunker.py`
- `src/personal_writing/material_library/embeddings.py`
- `src/personal_writing/material_library/retrieval.py`
- `src/personal_writing/material_library/reranker.py`
- `src/personal_writing/material_library/context_builder.py`
- `src/personal_writing/material_library/citation.py`
- `src/personal_writing/material_library/jobs.py`

前端模板：

- `src/personal_writing/web/templates/libraries.html`
- `src/personal_writing/web/templates/library_detail.html`
- `src/personal_writing/web/templates/library_document.html`
- `src/personal_writing/web/templates/partials/evidence_pack.html`
- `src/personal_writing/web/templates/partials/citation_panel.html`

测试：

- `tests/test_material_storage.py`
- `tests/test_material_extractors.py`
- `tests/test_material_chunker.py`
- `tests/test_material_retrieval.py`
- `tests/test_context_builder.py`
- `tests/test_pipeline_retrieval_hook.py`

文档：

- `docs/material-library-rd-plan.md`
- `docs/material-library-schema.md`
- `docs/material-library-api.md`
- `docs/material-library-privacy.md`

## 14. 推荐依赖

MVP：

- `pymupdf>=1.24`
- `pypdf>=4.0`
- `python-docx>=1.1`
- `beautifulsoup4>=4.12`
- `trafilatura>=1.8`
- `numpy>=1.26`

增强版：

- `sentence-transformers>=2.7`
- `faiss-cpu` 或 `sqlite-vec`，二选一，先评估本机安装成本。
- `readability-lxml>=0.8`

OCR 可选：

- `ocrmypdf`
- `pytesseract`

## 15. 风险和处理

- PDF 抽取质量不稳定：MVP 必须展示解析预览和失败状态，不要静默把乱码送进模型。
- 中文 FTS 效果有限：MVP 可接受，但增强版必须引入 embedding。
- embedding 依赖较重：允许 FTS-only 降级，设置页显示“向量检索未启用”。
- 引用格式复杂：MVP 先用 `[Sx]` 溯源，不急着做完整国标引文。
- 旧 `materials` 命名冲突：UI 文案要明确“历史素材”和“论文素材库”不同。
- 生成 prompt 过长：context builder 必须控制 evidence pack 总长度，按章节检索比一次塞满更可靠。
- 隐私风险：远程 embedding/模型调用要显式提示，不默认上传全文库。

## 16. 推荐立即启动的 8 个研发任务

1. 确定数据模型并写 SQLite migration，保留旧 `materials` 表。
2. 搭建 `material_library` 模块和 Repository。
3. 做本地文件存储和 PDF/Docx/Markdown/TXT 解析 MVP。
4. 实现 chunker 和 FTS5 搜索。
5. 新增素材库列表、详情、文档详情三个工作台页面。
6. 改造写作页，允许选择素材库和预览证据包。
7. 在 `pipeline.write(...)` 增加 retrieval hook，把 evidence pack 注入论文风格 prompt。
8. 建立 retrieval snapshot、文章引用解析和基础测试。

## 17. 阶段一 MVP 实施记录（2026-05-01）

已完成本地论文素材库 MVP 的第一版：

- 新增 `material_libraries`、`library_documents`、`document_chunks`、`generation_retrieval_snapshots`、`article_citations` 表，并尝试初始化 SQLite FTS5 虚表 `document_chunks_fts`；不支持 FTS5 时检索会降级为 `LIKE`。
- 新增 `src/personal_writing/material_library/` 模块：本地文件保存、sha256、安全文件名、txt/md/html/csv/xlsx/docx/pdf 解析、段落切片、关键词检索、evidence pack 组装。
- 写作 pipeline 新增 `library_ids`、`retrieval_query`、`library_mode` 参数；选择素材库时先检索证据包，并把带 `[S1]` 来源编号的证据注入 prompt。strict 模式要求证据不足写“需补证”。
- Web 新增路由：
  - `GET/POST /libraries`：素材库列表和新建。
  - `GET/POST /libraries/<library_id>`：上传/粘贴导入、文档状态、检索测试。
  - `GET /libraries/<library_id>/documents/<document_id>`：解析预览和切片预览。
  - `POST /api/v1/libraries/search`：素材库检索 API。
  - `POST /api/v1/write/preview-retrieval`：证据包预览 API。
- 写作页 `/` 增加论文素材库选择、检索问题、严格基于素材库开关。旧 `/materials` 历史输入页面保留。
- 新增 `tests/test_material_library_mvp.py`，覆盖 schema 初始化、创建素材库、导入文本材料、切片、检索、evidence pack 格式、pipeline 注入证据包。

使用方式：

1. 启动本地 Flask：`python -m personal_writing web --port 5566` 或 `./start-web.sh`。
2. 进入 `/libraries` 新建论文素材库。
3. 在素材库详情页上传文件或粘贴文本，确认文档状态为 `ready`。
4. 回到 `/` 写作页，选择素材库、填写检索问题，生成时会自动注入 evidence pack。

当前未做的增强项：

- embedding/向量检索和重排。
- OCR、扫描版 PDF 识别。
- 引用覆盖率核查和 `[Sx]` 到 chunk 的交互跳转。
- 文档元数据编辑、软删除、重试解析任务队列。

## 18. IMA-like 分类与文件夹架构计划（2026-05-01 增量）

用户反馈的关键问题是：论文素材库不能只是一个平铺文档列表，而应接近 IMA / NotebookLM 的资料库架构。乌鸦写作台的素材库应采用三层结构：

1. 素材库 / 知识库：对应一个论文、课题或长期研究项目，继续保留 `topic`、`discipline`、`citation_style`、`strict_grounding` 等字段，用来定义研究边界和默认引用约束。
2. 文件夹 / 分类：素材库内部的组织层级，可父子嵌套，例如“理论文献 / 平台治理”“规范材料 / 中国法”“案例与判决”。文件夹负责把资料放到一个可浏览的目录结构里。
3. 文档 / 资料：具体 PDF、Word、网页、Markdown、摘录或粘贴文本。文档可归入一个文件夹；旧数据允许 `folder_id` 为空，显示为“未分类”。

文件夹与标签 / 领域的分工：

- 文件夹用于组织层级，是“资料放在哪里”的问题。它适合模拟研究项目目录、论文资料包、证据分组和 NotebookLM 式 source collections。
- 标签 / 领域用于横向筛选，是“资料是什么属性”的问题。它可以跨文件夹标注“规范依据”“反方观点”“概念定义”“算法治理”“隐私权”等。当前 MVP 先在文档上预留 `tags` 字段，后续可升级为独立标签表。
- 素材库的 `topic` / `discipline` 仍作为库级研究范围，不替代文件夹，也不替代文档标签。

本次分类 MVP 已实现目标：

- 新增 `material_library_folders` 表，支持同一素材库内的父子文件夹：`library_id`、`parent_id`、`name`、`description`、`sort_order`、`created_at`、`updated_at`。
- `library_documents` 增加 `folder_id` 和低风险 `tags` 字段；旧文档无需迁移内容，默认显示为“未分类”。
- Repository 增加文件夹创建、列表、更新、树形读取和子树 ID 查询。
- 文档上传和粘贴导入可选择文件夹；文档列表可按文件夹过滤，点击父文件夹时包含其子文件夹资料。
- 检索 / 证据包继续支持全库检索，并预留和实现单库单文件夹范围检索；写作页可选择具体文件夹作为证据范围。
- `/libraries/<id>` 详情页改为左侧分类区 + 右侧导入、检索、文档列表，更接近 IMA/NotebookLM 的资料库工作台。

下一阶段仍待做：

- embedding / 向量检索：当前仍是 FTS5 优先、LIKE 降级，下一阶段需要本地 embedding 和混合检索重排。
- OCR：扫描版 PDF、图片型论文、截图材料仍需 OCR 降级链路。
- 引用核查：需要检查生成草稿中的 `[Sx]` 是否存在、是否真正支撑对应句子，并输出缺证报告。
- 标签系统：把当前文档 `tags` 字段升级为文档标签表和 UI 筛选器，支持跨文件夹领域筛选。
- 引用证据包可视化：让文章结果页的 `[Sx]` 可以跳回文档、页码、chunk 和原文片段。
