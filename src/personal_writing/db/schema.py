"""SQLite database schema and initialization."""

import sqlite3
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB_DIR = os.path.join(_PROJECT_ROOT, "data")
DB_PATH = os.path.join(DB_DIR, "personal_writing.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'paste'
        CHECK(source_type IN ('outline', 'paste', 'txt', 'url', 'obsidian')),
    raw_content TEXT NOT NULL DEFAULT '',
    content_type TEXT DEFAULT 'general'
        CHECK(content_type IN ('general', 'tech', 'legal', 'finance', 'personal')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft', 'processing', 'completed', 'archived'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL,
    prompt TEXT DEFAULT '',
    style_names TEXT NOT NULL DEFAULT '[]',
    headline_formula TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    style TEXT NOT NULL,
    title TEXT DEFAULT '',
    original_title TEXT DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    original_content TEXT DEFAULT '',
    headline_formula TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    published INTEGER NOT NULL DEFAULT 0,
    output_path TEXT DEFAULT '',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS styles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    config TEXT NOT NULL DEFAULT '{}',
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS style_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    style_id INTEGER NOT NULL,
    title TEXT DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    source TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (style_id) REFERENCES styles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS headline_formulas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    template TEXT NOT NULL DEFAULT '',
    suitable_styles TEXT NOT NULL DEFAULT '[]',
    description TEXT DEFAULT '',
    example TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS headline_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    headline TEXT NOT NULL,
    style TEXT DEFAULT '',
    note TEXT DEFAULT '',
    source TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS obsidian_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_path TEXT NOT NULL DEFAULT '',
    input_folders TEXT NOT NULL DEFAULT '[]',
    output_folder TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS common_phrases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase TEXT NOT NULL,
    category TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS review_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis TEXT NOT NULL,
    article_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS headline_generation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    content_preview TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    style TEXT DEFAULT '',
    result TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS material_libraries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    topic TEXT DEFAULT '',
    discipline TEXT DEFAULT '',
    citation_style TEXT DEFAULT 'inline_source_id',
    strict_grounding INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_material_libraries_updated_at
ON material_libraries(updated_at);

CREATE TABLE IF NOT EXISTS material_library_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id INTEGER NOT NULL,
    parent_id INTEGER DEFAULT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (library_id) REFERENCES material_libraries(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES material_library_folders(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_material_library_folders_library
ON material_library_folders(library_id, parent_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_material_library_folders_parent
ON material_library_folders(parent_id);

CREATE TABLE IF NOT EXISTS library_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id INTEGER NOT NULL,
    folder_id INTEGER DEFAULT NULL,
    title TEXT DEFAULT '',
    original_filename TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'paste',
    source_url TEXT DEFAULT '',
    mime_type TEXT DEFAULT '',
    sha256 TEXT DEFAULT '',
    author TEXT DEFAULT '',
    authors TEXT DEFAULT '[]',
    year TEXT DEFAULT '',
    publication_title TEXT DEFAULT '',
    doi TEXT DEFAULT '',
    abstract TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    attachment_path TEXT DEFAULT '',
    source TEXT DEFAULT '',
    zotero_key TEXT DEFAULT '',
    zotero_item_type TEXT DEFAULT '',
    published_at TEXT DEFAULT '',
    page_count INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    parse_status TEXT NOT NULL DEFAULT 'queued',
    parse_error TEXT DEFAULT '',
    text_preview TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (library_id) REFERENCES material_libraries(id) ON DELETE CASCADE,
    FOREIGN KEY (folder_id) REFERENCES material_library_folders(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_library_documents_library_id
ON library_documents(library_id);
CREATE INDEX IF NOT EXISTS idx_library_documents_sha256
ON library_documents(sha256);
CREATE INDEX IF NOT EXISTS idx_library_documents_status
ON library_documents(parse_status);

CREATE TABLE IF NOT EXISTS document_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    section_title TEXT DEFAULT '',
    page_start INTEGER DEFAULT 0,
    page_end INTEGER DEFAULT 0,
    char_start INTEGER DEFAULT 0,
    char_end INTEGER DEFAULT 0,
    locator TEXT DEFAULT '',
    text TEXT NOT NULL,
    char_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (library_id) REFERENCES material_libraries(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_library_id
ON document_chunks(library_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_page
ON document_chunks(page_start, page_end);
CREATE INDEX IF NOT EXISTS idx_document_chunks_chunk_index
ON document_chunks(document_id, chunk_index);

CREATE TABLE IF NOT EXISTS generation_retrieval_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    library_ids TEXT NOT NULL DEFAULT '[]',
    query TEXT NOT NULL DEFAULT '',
    retrieval_policy TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_generation_retrieval_snapshots_session
ON generation_retrieval_snapshots(session_id);

CREATE TABLE IF NOT EXISTS article_citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    snapshot_id INTEGER DEFAULT 0,
    source_label TEXT NOT NULL,
    document_id INTEGER NOT NULL,
    chunk_id INTEGER NOT NULL,
    quoted_text TEXT DEFAULT '',
    citation_text TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_article_citations_article
ON article_citations(article_id);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts
USING fts5(
    text,
    section_title,
    document_id UNINDEXED,
    library_id UNINDEXED,
    content='document_chunks',
    content_rowid='id'
);
"""


def get_connection():
    """Get a SQLite connection to the database."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # A packaged copy may start with an empty SQLite file if the app is opened
    # before the normal pipeline initialization path completes. Create the base
    # schema here too so read-only pages never fail with "no such table".
    has_styles = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'styles'"
    ).fetchone()
    if not has_styles:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(HEADLINE_FEEDBACK_TABLE_SQL)
        try:
            conn.executescript(FTS_SQL)
        except sqlite3.OperationalError:
            pass
        conn.commit()
    return conn


MIGRATIONS = [
    "ALTER TABLE articles ADD COLUMN original_content TEXT DEFAULT ''",
    "ALTER TABLE articles ADD COLUMN headline_candidates TEXT DEFAULT '[]'",
    "ALTER TABLE articles ADD COLUMN headline_selected TEXT DEFAULT ''",
    "ALTER TABLE articles ADD COLUMN previous_content TEXT DEFAULT ''",
    "ALTER TABLE articles ADD COLUMN original_title TEXT DEFAULT ''",
    "UPDATE articles SET original_title = title WHERE original_title IS NULL OR original_title = ''",
    "ALTER TABLE sessions ADD COLUMN title TEXT DEFAULT ''",
    "ALTER TABLE headline_generation_history ADD COLUMN content TEXT DEFAULT ''",
    "ALTER TABLE sessions ADD COLUMN library_ids TEXT DEFAULT '[]'",
    "ALTER TABLE sessions ADD COLUMN retrieval_policy TEXT DEFAULT '{}'",
    "ALTER TABLE sessions ADD COLUMN retrieval_snapshot_id INTEGER DEFAULT 0",
    "ALTER TABLE articles ADD COLUMN citation_summary TEXT DEFAULT '{}'",
    "ALTER TABLE articles ADD COLUMN grounding_status TEXT DEFAULT ''",
    "ALTER TABLE library_documents ADD COLUMN folder_id INTEGER DEFAULT NULL",
    "ALTER TABLE library_documents ADD COLUMN tags TEXT DEFAULT '[]'",
    "ALTER TABLE library_documents ADD COLUMN authors TEXT DEFAULT '[]'",
    "ALTER TABLE library_documents ADD COLUMN publication_title TEXT DEFAULT ''",
    "ALTER TABLE library_documents ADD COLUMN doi TEXT DEFAULT ''",
    "ALTER TABLE library_documents ADD COLUMN abstract TEXT DEFAULT ''",
    "ALTER TABLE library_documents ADD COLUMN notes TEXT DEFAULT ''",
    "ALTER TABLE library_documents ADD COLUMN attachment_path TEXT DEFAULT ''",
    "ALTER TABLE library_documents ADD COLUMN source TEXT DEFAULT ''",
    "ALTER TABLE library_documents ADD COLUMN zotero_key TEXT DEFAULT ''",
    "ALTER TABLE library_documents ADD COLUMN zotero_item_type TEXT DEFAULT ''",
    """CREATE INDEX IF NOT EXISTS idx_library_documents_year
       ON library_documents(year)""",
    """CREATE INDEX IF NOT EXISTS idx_library_documents_doi
       ON library_documents(doi)""",
    """CREATE INDEX IF NOT EXISTS idx_library_documents_zotero_key
       ON library_documents(zotero_key)""",
    """CREATE TABLE IF NOT EXISTS material_library_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        library_id INTEGER NOT NULL,
        parent_id INTEGER DEFAULT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        sort_order INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (library_id) REFERENCES material_libraries(id) ON DELETE CASCADE,
        FOREIGN KEY (parent_id) REFERENCES material_library_folders(id) ON DELETE SET NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_material_library_folders_library
       ON material_library_folders(library_id, parent_id, sort_order)""",
    """CREATE INDEX IF NOT EXISTS idx_material_library_folders_parent
       ON material_library_folders(parent_id)""",
    """CREATE INDEX IF NOT EXISTS idx_library_documents_folder_id
       ON library_documents(folder_id)""",
    """CREATE TABLE IF NOT EXISTS headline_library (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        headline TEXT NOT NULL,
        style TEXT DEFAULT '',
        note TEXT DEFAULT '',
        source TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )""",
]


# Headline selection feedback table (never auto-created, only via migration)
HEADLINE_FEEDBACK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS headline_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    material_id INTEGER DEFAULT 0,
    style TEXT DEFAULT '',
    headline TEXT NOT NULL,
    formula_name TEXT DEFAULT '',
    was_selected INTEGER NOT NULL DEFAULT 0,
    is_custom INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
);
"""


def init_db():
    """Initialize the database with schema and default data."""
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.executescript(HEADLINE_FEEDBACK_TABLE_SQL)
    try:
        conn.executescript(FTS_SQL)
    except sqlite3.OperationalError:
        pass

    # Run migrations (ignore errors if column already exists)
    for migration in MIGRATIONS:
        try:
            conn.execute(migration)
        except Exception:
            pass

    # Insert default built-in styles if not exist
    default_styles = [
        ("daily", "日常", "自言自语式的日常随笔，短句自嘲，自由跳跃", '{"word_count": 800, "sentence_length": "short", "tone": "casual", "structure": "free_flow", "paragraph_density": "tight", "rhetoric_density": "low", "personal_pronoun": "first_person", "humor_style": "self_deprecating", "ending_style": "open_ended"}', 1),
        ("sherry", "Sherry", "流深 Sherry 的公众号长文风格，温暖有说服力", '{"word_count": 2000, "sentence_length": "medium", "tone": "warm", "structure": "numbered_sections", "paragraph_density": "normal", "rhetoric_density": "medium", "personal_pronoun": "first_person", "humor_style": "dry", "ending_style": "summary"}', 1),
        ("short_science", "短科普", "客观亲切的短科普，一篇讲清楚一个东西", '{"word_count": 500, "sentence_length": "short_to_medium", "tone": "objective", "structure": "pain_point_to_solution", "paragraph_density": "normal", "rhetoric_density": "low", "personal_pronoun": "mixed", "humor_style": "none", "ending_style": "summary"}', 1),
        ("xiaohongshu", "小红书", "emoji点缀的短笔记，钩子开头+标签结尾", '{"word_count": 600, "sentence_length": "very_short", "tone": "casual", "structure": "hook_to_content", "paragraph_density": "tight", "rhetoric_density": "low", "personal_pronoun": "first_person", "humor_style": "dry", "ending_style": "open_ended"}', 1),
        ("zheng_ge_academic", "郑戈论文风格", "郑戈学术作者写作模型，适合生成法学选题、摘要、引言、提纲和章节论证", '{"word_count": 5000, "sentence_length": "long", "tone": "academic", "structure": "academic_paper", "paragraph_density": "dense", "rhetoric_density": "low", "personal_pronoun": "none", "humor_style": "none", "ending_style": "theoretical_summary", "category": "academic"}', 1),
    ]

    for name, display_name, description, config, is_builtin in default_styles:
        conn.execute(
            """INSERT OR IGNORE INTO styles (name, display_name, description, config, is_builtin)
               VALUES (?, ?, ?, ?, ?)""",
            (name, display_name, description, config, is_builtin),
        )

    # Insert default headline formulas
    default_formulas = [
        ("反常识断言", '"XX不XX，真正XX的是XX"', '["daily", "short_science"]', '颠覆读者固有认知的断言句式', '决定薪资的不是能力，是谈判'),
        ("第一人称+悬念", '"我用XX做了XX，然后..."', '["daily", "short_science", "xiaohongshu"]', '第一人称故事开头，省略号制造悬念', '我用AI帮自己写了一个AI，然后...'),
        ("身份+困境", '"XX的XX，困在XX"', '["sherry"]', '身份标签+困境描述，引发共鸣', '外卖骑手，困在系统里'),
        ("设问+痛点", '"为什么XX？"', '["short_science", "sherry"]', '从日常痛点出发发起设问', '为什么你在Claude Code花这么多钱？'),
        ("数字+对比", '"同一XX，两倍XX"', '["sherry", "short_science"]', '数字对比制造冲击感', '同一模型，两个工具，3倍token消耗'),
        ("痛点场景", '"我终于解决了XX问题"', '["daily", "xiaohongshu"]', '直接点出用户痛点，提供解决方案', '我终于解决了微信收藏夹吃灰的问题'),
        ("干货承诺", '"XX个XX，一看就懂"', '["xiaohongshu", "short_science"]', '数字+利益点，降低阅读门槛', '5个让你效率翻倍的AI工具'),
        ("身份+反转", '"我以为XX，结果XX"', '["daily", "xiaohongshu"]', '先建立预期再打破，制造好奇', '我以为命令行很难，结果真香'),
        ("场景素描", '"在XX，我看见/想起XX"', '["daily", "sherry"]', '用一个具体场景做标题，克制、有画面感，不夸张', '在香港，我想起一碗八块钱的肠粉'),
        ("物件留白", '"XX、XX，和XX"', '["daily", "sherry"]', '用几个具体物件并列，给读者留下想象空间', '菠萝包、冻奶茶，和十八块钱的失望'),
        ("普通句子", '"关于XX的一点记录"', '["daily", "sherry"]', '像日记或随笔标题，不制造强悬念', '关于香港吃饭的一点记录'),
        ("轻微转折", '"我以为XX，后来发现XX"', '["daily", "sherry"]', '保留个人经验里的变化，但不做夸张反转', '我以为香港很好吃，后来发现只是我想多了'),
        ("时间切片", '"XX之后/之前"', '["daily", "sherry"]', '用时间节点承接回忆，适合旅行、关系、阶段总结', '离开香港之后'),
        ("安静判断", '"XX这件小事"', '["daily", "sherry"]', '把主题压低，避免标题党，适合个人随笔和轻观点', '吃饭这件小事'),
    ]

    for name, template, suitable_styles, description, example in default_formulas:
        conn.execute(
            """INSERT OR IGNORE INTO headline_formulas (name, template, suitable_styles, description, example)
               VALUES (?, ?, ?, ?, ?)""",
            (name, template, suitable_styles, description, example),
        )

    conn.commit()
    conn.close()
