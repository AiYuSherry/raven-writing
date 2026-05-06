"""Processing pipeline — orchestrates the writing workflow."""

import json
import os
import re
from ..db.repository import MaterialRepo, SessionRepo, ArticleRepo, HeadlineFormulaRepo, HeadlineLibraryRepo, StyleRepo, StyleExampleRepo, ReviewAnalysisRepo, RetrievalSnapshotRepo, MaterialFolderRepo, get_connection
from ..db.schema import init_db
from ..material_library.context_builder import build_evidence_pack
from ..utils import claude_client
from .citation_verifier import verify_citations, format_report
from .citation_formatter import format_article_footnotes
from . import style_engine
from .input_reader import read_input
from .local_output import save_article as save_local_file


STRICT_ARTICLE_OUTPUT_RULES = """## 全局输出硬性规则
- 只输出可直接发布的文章正文。
- 不要输出任何对话、解释、评价、审稿意见、修改说明、改动说明、表格、清单、总结或元信息。
- 不要说“这篇文章已经……”“我做了……”“以下是……”“改动如下……”。
- 不要创建文件，不要保存到磁盘。
- 如果需要修改文章，只把修改后的全文写出来，不要附带原因。"""


EDIT_REPORT_PATTERNS = (
    "已在对话中输出修改后的完整文章",
    "主要处理了",
    "主要改动",
    "改动说明",
    "修改说明",
    "核心改动",
    "修改反馈",
    "审稿意见",
    "原文 | 修改 | 原因",
    "| 原文 |",
    "禁用句式",
    "微调了",
)


def looks_like_edit_report(text):
    """Return True when a rewrite result is an edit report, not article text."""
    if not text:
        return True
    probe = text.strip()[:900]
    strong = (
        "已在对话中输出修改后的完整文章",
        "主要处理了",
        "主要改动",
        "改动说明",
        "修改说明",
        "修改反馈",
        "| 原文 |",
    )
    if any(marker in probe for marker in strong):
        return True
    hits = sum(1 for marker in EDIT_REPORT_PATTERNS if marker in probe)
    bullet_lines = len(re.findall(r"(?m)^\s*[-*]\s+", probe))
    if hits >= 2 and bullet_lines >= 2:
        return True
    report_bullets = re.findall(r"(?m)^\s*[-*]\s*(?:\d+\s*处|功能列表|微调|删除|移除|改为|重写|保留|禁用)", probe)
    return bullet_lines >= 2 and len(report_bullets) >= 2


DAILY_FINAL_GUARDRAILS = """## 日常风格最终覆盖规则
这些规则优先级最高，如果和前文任何 prompt 冲突，以这里为准。
- 这不是公众号长文，不是 Sherry 风格，不要写成观点文、分析文、游记攻略或城市评价。
- 像一个人在给朋友讲自己的真实体验：短句，口语，具体，允许吐槽，允许自嘲。
- 不要小标题，不要分节标题，不要 Markdown 标题，不要“一、二、三”，不要“所以/结论/第一天：茶餐厅”这种独立标题行。
- 不要概括“香港是什么城市”，只写素材里具体那件事。用户说的是“香港的菜”，就只写吃到的东西和当时感受。
- 不要替用户扩展新主题，不要把“吃饭不好吃”扩成“艺术活动很好/城市精神生活丰富”，除非素材明确要求。
- 不要输出任何“我将按照”“编辑原则”“主要改动”“修改说明”。"""


HUMANIZER_SKILL_PATHS = [
    os.path.expanduser("~/.codex/skills/humanizer-zh/SKILL.md"),
    "",
]
_HUMANIZER_SKILL_CACHE = None


def _load_humanizer_skill():
    """Load the user's humanizer-zh skill when available."""
    global _HUMANIZER_SKILL_CACHE
    if _HUMANIZER_SKILL_CACHE is not None:
        return _HUMANIZER_SKILL_CACHE
    for path in HUMANIZER_SKILL_PATHS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            content = re.sub(r"^---[\s\S]*?---\s*", "", content).strip()
            _HUMANIZER_SKILL_CACHE = content
            return content
        except Exception:
            continue
    _HUMANIZER_SKILL_CACHE = ""
    return ""


def _format_rules_for_style(style_name):
    """Return format rules that do not conflict with the selected style."""
    if style_name == "daily":
        return """## 格式要求
- 不要使用任何小标题、分节标题、编号标题或 Markdown 标题。
- 不要写“第一天：茶餐厅”“菠萝包”“所以”这类独立成行的段落标题。
- 直接按日常随笔写成自然段，段落之间空行分隔。
- 可以换场景，但用正文自然转场，不要靠标题转场。"""
    if style_name == "xiaohongshu":
        return """## 格式要求
- 使用短段落，段落之间空行分隔。
- 可以保留小红书风格符号和话题标签，但不要输出写作说明。"""
    if style_name == "zheng_ge_academic":
        return """## 格式要求
- 默认输出论文型文本：题目、摘要、关键词、正文分节论证和结论。
- 正文用中文学术论文的节标题组织，可以使用“一、二、三”或 `##` 分节。
- 如果素材不足以支撑完整正文，必须在相应位置标注“需补证”，不要编造文献、法条、案例或页码。"""
    return """## 格式要求
- 正文用 `## 段落标题` 分节
- 小段可酌情用 `### 子标题`
- 正文段落之间空行分隔"""


def _mode_rules_for_style(style_name, generation_mode):
    """Return mode rules scoped to the current style."""
    if generation_mode == "thinking":
        if style_name == "daily":
            return """## 思考版要求（日常）
- 仍然只按“日常”风格写，不要变成公众号长文或分析文。
- 先在内部判断素材里真正有记忆点、情绪和细节的部分，但不要输出分析过程。
- 可以更认真地梳理顺序和情绪递进，但正文仍然像一个人自然说话。
- 保留素材原有图片与文字顺序。"""
        if style_name == "sherry":
            return """## 思考版要求（Sherry）
- 按完整 Sherry skill 工作流处理素材。
- 可以做更充分的选题判断、结构安排和自检，但不要输出思考过程。
- 质量优先，允许花更多时间打磨。"""
        if style_name == "short_science":
            return """## 思考版要求（短科普）
- 仍然只按“短科普”风格写，不要变成 Sherry 长文。
- 先在内部确认概念边界、误区和解释顺序，但不要输出分析过程。
- 用清楚的层次把一个问题讲明白。"""
        if style_name == "xiaohongshu":
            return """## 思考版要求（小红书）
- 仍然只按“小红书”风格写，不要变成公众号长文。
- 更认真地设计开头钩子、段落节奏和标签，但不要输出分析过程。"""
        if style_name == "zheng_ge_academic":
            return """## 思考版要求（郑戈论文风格）
- 按郑戈学术作者模型进行更充分的问题意识、概念重构和论证框架选择。
- 在内部检查事实层、文献层和作者模型层是否分离，但不要输出思考过程。
- 缺少规范、案例、文献或技术事实时，以“需补证”标出，不得补写虚假来源。"""
        return """## 思考版要求
- 只深化当前选中的风格，不要切换到其他风格。
- 可以在内部做结构判断和自检，但最终只输出正文。"""

    if style_name == "daily":
        return """## 快速版要求（日常）
- 只按日常风格快速出初稿。
- 不做额外分析，不输出思考过程。
- 直接保留素材里的主要顺序和细节。"""
    if style_name == "sherry":
        return """## 快速版要求（Sherry）
- 按 Sherry 风格快速出一版公众号初稿。
- 不展开完整工作流，不输出思考过程。
- 直接围绕素材组织成文。"""
    if style_name == "short_science":
        return """## 快速版要求（短科普）
- 按短科普风格快速出初稿。
- 聚焦一个概念或问题，不做额外长篇铺陈。"""
    if style_name == "xiaohongshu":
        return """## 快速版要求（小红书）
- 按小红书风格快速出初稿。
- 短段落、轻表达，直接可发。"""
    if style_name == "zheng_ge_academic":
        return """## 快速版要求（郑戈论文风格）
- 按郑戈论文风格快速生成可继续修改的论文型初稿。
- 至少包含题目、摘要、关键词和分节提纲/正文骨架。
- 不做虚假检索，不编造文献、法条、案例或页码。"""
    return """## 快速版要求
- 只按当前选中的风格快速出初稿。
- 不输出思考过程。"""


def init():
    """Initialize the database and register built-in styles."""
    init_db()
    register_builtin_styles()


def register_builtin_styles():
    """Register all built-in styles."""
    from ..styles.daily import DailyStyle
    from ..styles.sherry import SherryStyle
    from ..styles.short_science import ShortScienceStyle
    from ..styles.xiaohongshu import XiaohongshuStyle
    from ..styles.zheng_ge_academic import ZhengGeAcademicStyle

    registry = style_engine.registry
    registry.register(DailyStyle)
    registry.register(SherryStyle)
    registry.register(ShortScienceStyle)
    registry.register(XiaohongshuStyle)
    registry.register(ZhengGeAcademicStyle)


def write(raw_input, style_names=None, generation_mode="fast", library_ids=None, retrieval_query="", library_mode="material_first", folder_id=None):
    """Main entry point: process input and generate articles in specified styles.

    Args:
        raw_input: Raw text, file path, or URL
        style_names: List of style names to generate.
                     If None, generates in all available styles.

    Returns:
        Dict with material_id, session_id, and generated articles.
    """
    # 1. Read input
    content, source_type, title = read_input(raw_input)
    if not content:
        raise ValueError("Empty input")

    # 2. Save material
    material_id = MaterialRepo.create(
        title=title,
        source_type=source_type,
        raw_content=content,
    )
    MaterialRepo.update_status(material_id, "processing")

    # 3. Determine styles
    if style_names is None or len(style_names) == 0:
        style_names = [s["name"] for s in style_engine.registry.list_info()]

    # 4. Create session and optional retrieval snapshot
    selected_library_ids = [int(x) for x in (library_ids or []) if str(x).strip()]
    selected_folder_id = int(folder_id) if folder_id not in (None, "", 0, "0") else None
    selected_folder_name = ""
    if selected_folder_id:
        folder = MaterialFolderRepo.get(selected_folder_id)
        if folder and folder["library_id"] in selected_library_ids:
            selected_folder_name = folder.get("name", "")
            selected_library_ids = [folder["library_id"]]
        else:
            selected_folder_id = None
    retrieval_policy = {}
    if selected_library_ids:
        retrieval_policy = {"mode": library_mode or "material_first", "top_k": 8}
        if selected_folder_id:
            retrieval_policy["folder_id"] = selected_folder_id
    session_id = SessionRepo.create(
        material_id=material_id,
        style_names=style_names,
        library_ids=selected_library_ids,
        retrieval_policy=retrieval_policy,
    )

    evidence = None
    snapshot_id = 0
    if selected_library_ids:
        query = (retrieval_query or "").strip() or _default_retrieval_query(content, style_names)
        evidence = build_evidence_pack(
            selected_library_ids,
            query=query,
            mode=library_mode or "material_first",
            top_k=retrieval_policy["top_k"],
            folder_id=selected_folder_id,
            folder_name=selected_folder_name,
        )
        snapshot_id = RetrievalSnapshotRepo.create(
            session_id=session_id,
            library_ids=selected_library_ids,
            query=query,
            retrieval_policy=retrieval_policy,
            evidence=evidence,
        )

    # 5. Generate articles for each style
    results = []
    for sname in style_names:
        style = style_engine.registry.get(sname)
        if style is None:
            results.append({
                "style": sname,
                "title": "",
                "content": f"[未找到风格: {sname}]",
                "error": f"Style '{sname}' not found",
            })
            continue

        try:
            article = generate_one(
                style,
                content,
                generation_mode=generation_mode,
                evidence_pack=(evidence or {}).get("pack", ""),
                library_mode=library_mode or "material_first",
            )
            # Headline generation is another Codex call. Keep fast mode to one
            # model call per article; thinking mode can spend the extra time.
            candidates = []
            if generation_mode == "thinking":
                candidates = generate_headline_candidates(content, article.get("content", ""), sname)

            # Save article to DB
            article_id = ArticleRepo.create(
                session_id=session_id,
                style=sname,
                title=article.get("title", ""),
                content=article.get("content", ""),
                headline_formula=article.get("formula", ""),
            )
            if candidates:
                ArticleRepo.save_headline_candidates(article_id, candidates)

            # Save local copy in project 草稿 folder
            local_path = save_local_file(
                article_id=article_id,
                style=sname,
                title=article.get("title", ""),
                content=article.get("content", ""),
                session_id=session_id,
            )
            if local_path:
                ArticleRepo.set_output_path(article_id, local_path)
            citation_verification_result = None
            if snapshot_id:
                # Run citation verification against evidence
                try:
                    citation_verification_result = verify_citations(
                        article_id,
                        snapshot_id=snapshot_id,
                        evidence_results=(evidence or {}).get("results", []),
                    )
                    grounding_status = citation_verification_result.grounding_status
                except Exception:
                    grounding_status = "not_checked"

                ArticleRepo.set_grounding(
                    article_id,
                    citation_summary={
                        "snapshot_id": snapshot_id,
                        "source_labels": [item["label"] for item in (evidence or {}).get("results", [])],
                        "verification": (
                            citation_verification_result.to_dict()
                            if citation_verification_result
                            else None
                        ),
                    },
                    grounding_status=grounding_status,
                )

                # Format [Sx] → footnotes and save to DB
                try:
                    formatted_content, footnotes_str = format_article_footnotes(
                        article.get("content", ""),
                        (evidence or {}).get("results", []),
                    )
                except Exception:
                    formatted_content = article.get("content", "")
                    footnotes_str = ""
                # Append footnotes section to formatted content
                if footnotes_str:
                    formatted_content = formatted_content.rstrip() + "\n\n" + footnotes_str
                # Persist formatted content back to article
                if formatted_content and formatted_content != article.get("content", ""):
                    conn2 = get_connection()
                    conn2.execute(
                        "UPDATE articles SET content = ?, original_content = ? WHERE id = ?",
                        (formatted_content, article.get("content", ""), article_id),
                    )
                    conn2.commit()
                    conn2.close()
            else:
                formatted_content = article.get("content", "")
                footnotes_str = ""

            results.append({
                "id": article_id,
                "style": sname,
                "title": article.get("title", ""),
                "content": formatted_content,
                "formatted_content": formatted_content,
                "footnotes": footnotes_str,
                "formula": article.get("formula", ""),
                "headline_candidates": candidates,
                "retrieval_snapshot_id": snapshot_id,
                "evidence": (evidence or {}).get("results", []),
                "citation_verification": (
                    citation_verification_result.to_dict() if citation_verification_result else None
                ),
            })
        except Exception as e:
            results.append({
                "style": sname,
                "title": "",
                "content": "",
                "error": str(e),
            })

    # 6. Update status
    MaterialRepo.update_status(material_id, "completed")

    return {
        "material_id": material_id,
        "session_id": session_id,
        "retrieval_snapshot_id": snapshot_id,
        "articles": results,
    }


def _default_retrieval_query(content, style_names=None):
    style_hint = " ".join(style_names or [])
    text = re.sub(r"\s+", " ", content or "").strip()
    if len(text) > 500:
        text = text[:500]
    return f"{style_hint} {text}".strip()


def _evidence_prompt_section(evidence_pack, library_mode):
    if not evidence_pack:
        return ""
    if library_mode == "strict":
        rules = """## 素材库严格模式
- 事实性陈述只能来自“素材库证据包”，并在句末标注对应 [Sx]。
- 证据包没有的文献、法条、案例、页码、数据、机构判断，不得补写或猜测。
- 论证结构和语言风格可以按当前风格处理；事实来源必须以证据包为准。
- 证据不足但结构上需要的位置，写“需补证：缺少xxx材料”。
- 引用格式：[Sx] 必须紧跟在被引用内容之后，不得脱离原文单独标注。
- 每个 [Sx] 对应的内容必须在证据包中有明确原文支撑，不得编造。
- 如需引用具体页码，在 [Sx] 后标注“（第X页）”，且该页码必须在证据所覆盖范围内。
"""
    elif library_mode == "search_only":
        rules = """## 素材库检索模式
- 下面证据只作为检索参考；如使用其中事实，请保留 [Sx] 来源标记。
- 不要编造证据包之外的具体文献、页码、案例或数据。
- [Sx] 标记必须对应证据包中真实存在的切片，不得凭空标注。
"""
    else:
        rules = """## 素材库优先模式
- 优先使用“素材库证据包”支持事实性陈述，并尽量在句末标注 [Sx]。
- 证据包之外的具体文献、法条、案例、页码和数据不得编造。
- 证据不足时写“需补证”，不要用风格模型替代事实来源。
- 标注为 [Sx] 的内容必须在证据包中有对应的原文片段可查证。
"""
    return f"{rules}\n{evidence_pack}\n"


def _clean_output(text):
    """Remove common AI output artifacts."""
    import re
    if not text:
        return ""
    # Remove AI preamble phrases ("好的，以下是文章：", "以下是文章：", "好的：", etc.)
    text = re.sub(r'^(好的[，,]\s*)?以下[是:：].*?[：:]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^根据要求[，,].*?[：:]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^(好的[，,]\s*)?(这是|为你|给你).*?[：:]\s*', '', text, flags=re.MULTILINE)
    # Remove entire first line if it's a short AI preamble line
    _first_split = text.split('\n', 1)
    _first_line = _first_split[0].strip()
    if _first_line and len(_first_line) < 140 and re.search(
        r'(^(好的|没问题|当然|明白了|收到|根据|这是|给你|为你|以下|写好了|文章已经|文章约|已在))'
        r'|(以下是)|(好的[，,])|(根据你的)|(这是你需要的)'
        r'|(为你写)|(我来为你)|(下面[是为给])'
        r'|(我[已]?经[为给]?)|(这篇[文章篇])|(直接输出)|(这是修改)'
        r'|(没有.*AI痕迹)|(可以打磨)|(我还是找到)|(我将按照)|(按照上述)',
        _first_line,
    ):
        text = _first_split[1] if len(_first_split) > 1 else ''
    # Drop appended notes / edit reports accidentally returned with the article.
    text = re.split(
        r'(?:^|\n|\s{2,}|\s)\**\s*(主要处理了|主要改动|改动说明|修改说明|核心改动|核心修改|修改反馈|审稿意见|备注)\s*[：:]\s*\**',
        text,
        maxsplit=1,
    )[0]
    text = re.split(r'\n\s*\|\s*原文\s*\|\s*修改\s*\|\s*原因\s*\|', text, maxsplit=1)[0]
    # Remove "好的，", "没问题", "当然" standalone preambles
    text = re.sub(r'^(好的[，,!\s]*|没问题[，,!\s]*|当然[，,!\s]*)\n+', '', text)
    # Remove === filename === markers
    text = re.sub(r'^={3,}\s*.+?\s*={3,}\s*$', '', text, flags=re.MULTILINE)
    # Remove "写好了，保存在..." type lines
    text = re.sub(r'^写好了，保存在.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^文章[已经]?保存[到至].*$', '', text, flags=re.MULTILINE)
    # Remove "文章约" prefixed lines
    text = re.sub(r'^文章约\d+字.*$', '', text, flags=re.MULTILINE)
    # Remove --- separators
    text = re.sub(r'\n-{3,}\n', '\n', text)
    # Remove leading/trailing whitespace per line
    lines = [l.strip() for l in text.split('\n')]
    # Remove empty lines at start/end, collapse multiple empty lines
    result = []
    prev_empty = False
    for l in lines:
        if not l:
            if not prev_empty:
                result.append('')
            prev_empty = True
        else:
            result.append(l)
            prev_empty = False
    return '\n'.join(result).strip()


def _strip_daily_headings(text):
    """Remove section-like headings from daily pieces while preserving paragraphs."""
    if not text:
        return ""
    cleaned = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            cleaned.append("")
            continue
        if re.match(r"^#{1,6}\s+", line):
            continue
        plain = re.sub(r"^[#>*\-\s]+", "", line).strip()
        # Drop short standalone labels such as "菠萝包", "所以", "第一天：茶餐厅".
        if len(plain) <= 18 and not re.search(r"[。！？.!?，,；;]", plain):
            if re.search(r"^(第[一二三四五六七八九十\d]+[天顿站次]?[:：]|所以$|结论$|总结$|菠萝包$|冻奶茶$|茶餐厅$)", plain):
                continue
        cleaned.append(line)
    return _clean_output("\n".join(cleaned))


def generate_one(style, content, generation_mode="fast", evidence_pack="", library_mode="material_first"):
    """Generate one article using a specific style.

    Args:
        style: A BaseStyle instance
        content: The raw material content

    Returns:
        Dict with 'title', 'content', 'formula'
    """
    config = style.get_config()
    is_thinking = generation_mode == "thinking"
    # Sherry quality is best when the complete local SKILL.md drives the task.
    # DB prompt edits can be truncated optimization summaries, so do not let
    # them replace the full skill for the built-in Sherry style.
    if style.name == "sherry":
        prompt_template = style.get_prompt_template()
    else:
        prompt_template = config.get("prompt_template") or style.get_prompt_template()
    format_rules = _format_rules_for_style(style.name)
    mode_rules = _mode_rules_for_style(style.name, generation_mode)
    evidence_section = _evidence_prompt_section(evidence_pack, library_mode)

    # Include past review analysis as reference context. Daily writing is easily
    # over-edited by cross-style review notes, so keep it prompt-only.
    review_context = "" if (style.name in ("daily", "zheng_ge_academic") or not is_thinking) else get_latest_analysis_context()
    review_section = f"""
## 过往写作建议参考
{review_context}
""" if review_context else ""

    # Build writing prompt
    # For Sherry style, SKILL.md is self-contained — just append material as the task
    if style.name == "sherry":
        if is_thinking:
            write_prompt = f"""{prompt_template}

## 本次写作任务
请按照上面的 Sherry skill 完整工作流处理下面素材，写成一篇可直接发布的公众号长文。

{mode_rules}

重要要求：
- 保留素材里图片与文字的相对顺序。看到 Markdown 图片（`![说明](路径)`）时，把它当作当前位置的配图，不要挪到文末，不要只输出图片文件名。
- 如果素材本身已经有标题、段落、图片顺序，尽量沿用原来的排版骨架，在这个基础上润色和扩写。
- 输出正文，不要解释你做了什么，不要写修改说明，不要创建文件。

{evidence_section}

## 素材内容
{content}

{STRICT_ARTICLE_OUTPUT_RULES}

{review_section}
"""
        else:
            write_prompt = f"""{prompt_template}

## 本次写作任务
请基于下面素材，按 Sherry 风格写一篇可直接发布的公众号文章初稿。

{mode_rules}

重要要求：
- 保留素材里图片与文字的相对顺序。看到 Markdown 图片（`![说明](路径)`）时，把它当作当前位置的配图。
- 尽量沿用素材原有标题、段落和图片顺序，只做必要润色和组织。
- 直接输出正文，不要解释，不要写修改说明，不要创建文件。

{evidence_section}

## 素材内容
{content}

{STRICT_ARTICLE_OUTPUT_RULES}
"""
    elif style.name == "daily":
        write_prompt = f"""{prompt_template}

{DAILY_FINAL_GUARDRAILS}

{mode_rules}

{evidence_section}

## 素材内容
{content}

{STRICT_ARTICLE_OUTPUT_RULES}

## 写作要求
- 目标字数：约{config.get('word_count', 800)}字
- 语气：口语、自嘲、具体，不要公众号长文腔
- 结构：自然段，不分节
- 人称视角：{config.get('personal_pronoun', 'first_person')}
{format_rules}
请先写一个短标题，再写正文。不要创建任何文件，不要保存到磁盘，不要额外解释。"""
    elif style.name == "zheng_ge_academic":
        write_prompt = f"""{prompt_template}

## 本次写作任务
请基于下面素材，按“郑戈论文风格”生成一篇法学论文型文本或论文草稿。

{mode_rules}

{evidence_section}

## 素材内容
{content}

## 输出硬性规则
- 只输出论文型正文，不要解释你做了什么，不要输出修改说明，不要创建文件。
- 不代表郑戈本人观点，不得冒充郑戈本人新作，不署郑戈名。
- 不编造文献、法条、案例、页码、政策文本、数据或新近事实。
- 素材没有给出且你无法核验的事实、规范、案例或文献，用“需补证：...”明确标记。
- 必须区分事实层、文献层和作者模型层：事实来自素材，文献观点来自素材，郑戈模型只提供问题意识、概念重构、论证节奏和表达方式。

## 写作要求
- 目标字数：约{config.get('word_count', 5000)}字；如果素材不足，先输出高质量题目、摘要、关键词和三级提纲。
- 语气：严肃、克制、法学论文风格。
- 结构：题目、摘要、关键词、引言、分节论证、结论。
{format_rules}
"""
    else:
        write_prompt = f"""{prompt_template}

{evidence_section}

## 素材内容
{content}

{mode_rules}

{STRICT_ARTICLE_OUTPUT_RULES}

## 写作要求
- 目标字数：约{config.get('word_count', 1000)}字
- 语气：{config.get('tone', 'natural')}
- 结构：{config.get('structure', 'free')}
- 人称视角：{config.get('personal_pronoun', 'first_person')}{review_section}
{format_rules}
请先写标题，再写正文。不要创建任何文件，不要保存到磁盘，不要额外解释。"""

    # Call Claude Code
    if not claude_client.is_available():
        raise RuntimeError("Claude Code CLI not found. Install it first.")

    response = claude_client.call(write_prompt)

    # Clean output artifacts FIRST (AI preamble, file markers, etc.)
    response = _clean_output(response)

    # Parse title and content
    title = ""
    body = response
    lines = response.strip().split("\n", 1)
    if lines[0].startswith("# "):
        title = lines[0][2:].strip()
        body = lines[1] if len(lines) > 1 else ""
    elif lines[0].startswith("#"):
        title = lines[0][1:].strip()
        body = lines[1] if len(lines) > 1 else ""
    else:
        # Use first line as title if short enough
        first_line = lines[0].strip()[:80]
        if first_line and len(first_line) < 60:
            title = first_line

    # Post-process
    if hasattr(style, "post_process"):
        body = style.post_process(body)
    if style.name == "daily":
        body = _strip_daily_headings(body)

    # Auto-humanize for long/expository styles. Daily has its own compact prompt;
    # the generic editor tends to turn it into a polished long-form essay.
    if is_thinking and style.name in ("sherry", "short_science"):
        # Include reference examples if available
        db_style = StyleRepo.get_by_name(style.name)
        examples = StyleExampleRepo.list_by_style(db_style["id"]) if db_style else []
        body = _humanize(body, style.name, examples)
        body = _clean_output(body)

    return {
        "title": title,
        "content": body or response,
        "formula": "",
    }


def _humanize(text, style_name, examples=None):
    """Polish article through humanizer-zh to remove AI writing痕迹.

    Uses Codex CLI with the humanizer-zh prompt to make text
    sound more natural and human-written.

    Args:
        text: The article text to polish
        style_name: Style name for context
        examples: Optional list of reference examples dicts (from DB)

    Returns:
        Polished text
    """

    # Build reference examples section if available
    ref_section = ""
    if examples:
        ref_parts = []
        for i, ex in enumerate(examples[:3], 1):  # Max 3 examples
            ex_title = ex.get("title", "") or f"参考{i}"
            ex_content = ex["content"][:1500]
            ref_parts.append(f"### {ex_title}\n{ex_content}")
        if ref_parts:
            ref_section = f"""
## 你的写作风格参考（请模仿以下示例的语感和用词）

下面是你自己写的文章，请仔细分析模仿其中的语言风格、节奏和用词习惯，让润色后的文字听起来更像你本人写的：

{"".join(ref_parts)}

"""

    style_specific_output_rules = ""
    if style_name == "daily":
        style_specific_output_rules = """
- 日常风格禁止小标题、分节标题、编号标题和 Markdown 标题；不要保留独立成行的“菠萝包”“所以”这类段落标题。
- 如果原文已有小标题，把它们自然融入正文或删除，不要另起标题。
"""
    else:
        style_specific_output_rules = "- 保留原有 Markdown 标题层级，尤其是 `#`、`##`、`###`"

    humanizer_skill = _load_humanizer_skill()
    humanizer_prompt = f"""{humanizer_skill}

## 本次任务补充
你现在只做“去 AI 痕迹的轻润色”，不要重写选题，不要改变文章结构，不要挪动 Markdown 图片位置。
尤其注意：
- 破折号不要滥用。除非语气上必须停顿，优先改成逗号、句号、冒号或括号；全文破折号尽量不超过 2 处。
- 不要输出修改说明、分析表格、主要改动。
- 保留所有 Markdown 图片行 `![...](...)` 的原位置。
- Sherry 风格要保留流深式的温和、清楚、分层表达，不要改成泛泛公众号腔。

下面是旧版内置规则，仍可参考：

你是一位文字编辑，专门识别和去除 AI 生成文本的痕迹，使文字听起来更自然、更有人味。

## 核心原则

1. **删除填充短语** - 去除开场白和强调性拐杖词
2. **打破公式结构** - 避免二元对比、戏剧性分段、修辞性设置
3. **变化节奏** - 混合句子长度。两项优于三项。段落结尾要多样化
4. **信任读者** - 直接陈述事实，跳过软化、辩解和手把手引导
5. **删除金句** - 如果听起来像可引用的语句，重写它

## 需要检测和修复的模式

1. **过度强调意义** - 删除"标志着""见证了""是……的体现""至关重要""关键作用""不断演变的格局"等词汇
2. **宣传广告式语言** - 删除"充满活力的""深刻的""开创性的""令人叹为观止的""必游之地"等
3. **模糊归因** - 删除"行业报告显示""专家认为""一些批评者认为"等无具体来源的归因
4. **AI 高频词汇** - 删除"此外""与……保持一致""深入探讨""持久的""格局""复杂/复杂性""关键性的"等
5. **系动词回避** - 将"作为/代表/标志着/充当"替换为"是/有"
6. **否定式排比** - 避免"不仅……而且……""这不仅仅是……而是……"
7. **三段式法则** - 避免强行将想法分成三组；改为两项或四项
8. **破折号过度使用** - 减少破折号使用频率
9. **填充短语** - "为了实现这一目标"→"为了实现"，"值得注意的是"→删除
10. **过度限定** - "可以潜在地可能被认为"→"可能会"
11. **通用积极结论** - 删除模糊的乐观结尾，用具体事实替代
12. **以-ing结尾的肤浅分析** - 删除"突出/强调/彰显……""确保……""反映/象征……"
13. **表情符号** - 删除或减少表情符号使用
14. **协作交流痕迹** - 删除"希望这对您有帮助""当然！"等对话痕迹
15. **日积月累式总结** - 删除"单个看不算什么，但日积月累……"这类强行升华的公式
16. **否定式定义** - 删除"不是那种……的……"句式，直接说是什么
17. **模板化结尾** - 删除"如果你也有……不妨……说不定……""不妨试试"等模板号召
18. **引导词** - 删除"也值得提""另外""值得一提的是"等冗余引导，直接陈述
19. **鸡血收尾** - 删除"省下那几分钟""从今天开始"等励志式结尾，用具体陈述收束

## 个性与灵魂

除了去除 AI 模式，还要注入真实感：
- 有观点 - 不要只报告事实，对它们做出反应
- 变化节奏 - 短促有力的句子和长句混合使用
- 承认复杂性 - 真实的人有复杂的感受
- 允许一些混乱 - 完美的结构感觉像算法
- 使用具体细节而不是模糊的主张
{ref_section}
## 待处理的文章（{style_name} 风格）
{text[:12000]}

## 输出要求
- 直接输出修改后的完整文章（全文）
- 保持核心信息完整
{style_specific_output_rules}
- 禁止输出“改动说明”“修改说明”“核心改动”“表格”“原因”
- 不要额外解释，不要创建任何文件，不要保存到磁盘"""

    if not claude_client.is_available():
        return text

    try:
        result = claude_client.call(humanizer_prompt)
        if result and result.strip():
            # Remove any explanatory prefix if present
            cleaned = result.strip()
            # If the response includes markdown code fences, extract content
            if "```" in cleaned:
                parts = cleaned.split("```")
                for p in parts:
                    p = p.strip()
                    if p and not p.startswith("markdown") and not p.startswith("text"):
                        cleaned = p
                        break
            return cleaned
    except Exception:
        pass
    return text


def generate_headline_candidates(content, article_text, style_name=None):
    """Generate at least 5 headline candidates for an article.

    Args:
        content: The original material content
        article_text: The generated article text (for context)
        style_name: Optional style name to filter suitable formulas

    Returns:
        List of dicts: [{"headline": "...", "formula": "..."}, ...]
    """
    if style_name:
        formulas = HeadlineFormulaRepo.list_by_style(style_name)
    else:
        formulas = HeadlineFormulaRepo.list_all()

    formula_descs = "\n".join(
        [f"- {f['name']}: {f['template']}（例如：{f['example']}）" for f in formulas]
    )
    saved_headlines = HeadlineLibraryRepo.list(style_name or "", limit=12)
    saved_headline_descs = "\n".join(
        [
            f"- {h['headline']}"
            + (f"（{h['note']}）" if h.get("note") else "")
            for h in saved_headlines
        ]
    )

    title_tone = "标题要自然、克制，优先给出日记感、文艺感、书名感的正常标题；不要标题党，不要强行悬念。" if style_name == "daily" else "标题要自然、准确，有吸引力但不要夸张标题党。"

    prompt = f"""根据以下素材和已生成的文章，生成至少 5 个文章标题候选。

## 素材内容
{content[:1500]}

## 已生成的文章（节选）
{article_text[:1000]}

## 参考标题公式
{formula_descs}

## 我积累过的好标题
{saved_headline_descs or "暂无。"}

要求：
1. 至少生成 5 个标题
2. 每个标题标注使用了哪个公式（或标注"自由创作"）
3. 标题要符合文章内容，不要跑题
4. **硬性约束：每个标题必须在 20 字以内（超出则无效，会被自动丢弃）**
5. 不要创建任何文件，不要保存到磁盘
6. {title_tone}

请严格按以下格式输出（不要额外解释）：
## 标题候选
1. [标题] — 公式：[公式名]
2. [标题] — 公式：[公式名]
...
"""

    if not claude_client.is_available():
        raise RuntimeError("Claude Code CLI not found.")

    response = claude_client.call(prompt)

    # Parse structured results
    candidates = []
    for line in response.split("\n"):
        line = line.strip()
        # Match patterns like: "1. 标题内容 — 公式：公式名"
        m = re.match(r'^\d+[\.\s]+\|?(.+?)\s*[—\-–]\s*公式[：:]?\s*(.+)', line)
        if m:
            headline = m.group(1).strip().strip('"').strip('"').strip("「").strip("」")
            formula = m.group(2).strip().strip('"').strip('"')
            candidates.append({"headline": headline, "formula": formula})
            continue
        # Match patterns like: "1. [标题] — 公式：公式名"
        m = re.match(r'^\d+[\.\s]+\|?「(.+)」\s*[—\-–]\s*公式[：:]?\s*(.+)', line)
        if m:
            candidates.append({"headline": m.group(1).strip(), "formula": m.group(2).strip()})
            continue

    # Fallback: if parsing failed, try extracting any numbered list
    if not candidates:
        for line in response.split("\n"):
            line = line.strip()
            m = re.match(r'^\d+[\.\s]+\|?(.+)', line)
            if m:
                candidates.append({"headline": m.group(1).strip(), "formula": ""})

    # Hard filter: enforce 20-character limit
    before = len(candidates)
    candidates = [c for c in candidates if len(c["headline"]) <= 20]
    if candidates and before != len(candidates):
        pass  # silently drop over-length titles

    return candidates[:10]  # Max 10


def generate_headlines(content, style_name=None):
    """Generate candidate headlines for the given content (legacy / CLI use).

    Args:
        content: The material content
        style_name: Optional style name to filter suitable formulas

    Returns:
        List of (headline, formula_name) tuples.
    """
    candidates = generate_headline_candidates(content, content, style_name)
    return [(c["headline"], c["formula"]) for c in candidates]


def generate_writing_review(limit=20):
    """Analyze edited articles and generate a writing improvement review.

    Compares original_content vs current content across recent edited articles,
    identifies patterns in the user's edits, and suggests improvement areas.

    Args:
        limit: Max articles to review

    Returns:
        Dict with review_data (list of edited articles) and analysis (AI-generated insights).
    """
    from ..db.schema import get_connection

    conn = get_connection()
    rows = conn.execute(
        """SELECT id, style, title, content, original_content, created_at
           FROM articles
           WHERE content != original_content AND original_content != ''
           ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()

    edited_articles = [dict(r) for r in rows]
    if not edited_articles:
        return {
            "count": 0,
            "articles": [],
            "analysis": "暂无已修改的文章。编辑文章并保存后，再来回顾吧。",
        }

    # Build analysis prompt
    changes_summary = []
    for a in edited_articles[:10]:  # Max 10 for analysis
        orig = a.get("original_content", "")[:500]
        curr = a.get("content", "")[:500]
        changes_summary.append(
            f"## 《{a['title'] or '无标题'}》（{a['style']}风格）\n"
            f"原文开头：{orig}\n"
            f"修改后开头：{curr}\n"
        )

    analysis_prompt = f"""以下是我最近修改的 {len(edited_articles)} 篇文章，每篇都列出了修改前后的开头部分。

请分析我的修改习惯，给出写作提升建议：

{chr(10).join(changes_summary)}

请从以下角度分析：
1. ✂️ 修改模式：我倾向于修改哪些部分（开头/结尾/措辞/结构）？
2. 💪 优势：我的修改中体现了哪些写作优点？
3. 🎯 改进空间：有什么共性问题可以改进？
4. ⚡ 具体建议：给出 2-3 条最实用的写作提升建议

简洁直接，不要废话。"""

    analysis = ""
    if claude_client.is_available():
        try:
            analysis = claude_client.call(analysis_prompt)
            # Save to DB for future reference
            ReviewAnalysisRepo.save(analysis, len(edited_articles))
        except Exception:
            analysis = "AI 分析暂时不可用。"

    return {
        "count": len(edited_articles),
        "articles": edited_articles[:limit],
        "analysis": analysis,
    }


def get_review_analysis_history(limit=5):
    """Get recent review analyses for display."""
    return ReviewAnalysisRepo.get_latest(limit)


def get_latest_analysis_context():
    """Get the latest analysis summary for injection into article generation."""
    analyses = ReviewAnalysisRepo.get_latest(3)
    if not analyses:
        return ""
    parts = []
    for a in analyses:
        # Extract key insights (first ~300 chars of each)
        text = a["analysis"][:300]
        parts.append(f"[{a['created_at']}] {text}")
    return "\n\n".join(parts)
