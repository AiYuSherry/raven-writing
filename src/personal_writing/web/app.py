"""Flask web application for Personal Writing."""

import os
import json
import tempfile
import subprocess
import base64
import re
import uuid
import hashlib
import difflib
from flask import Flask, render_template, request, jsonify

from ..core import pipeline
from ..core.input_reader import read_spreadsheet, read_epub
from ..core.pipeline import _clean_output, _format_rules_for_style, _strip_daily_headings, _repair_hard_constraint_violations, _hard_enforce_output, _violates_hard_constraints, looks_like_edit_report, DAILY_FINAL_GUARDRAILS, STRICT_OUTPUT_RULES, HARD_CONSTRAINT_REPAIR_RULES, _sanitize_style_prompt_template
from ..core.style_engine import registry as style_registry
from ..core.obsidian_bridge import archive_to_works
from ..db.repository import MaterialRepo, SessionRepo, ArticleRepo, HeadlineFeedbackRepo, HeadlineLibraryRepo, HeadlineAnalysisRepo, HeadlineFormulaRepo, CommonPhraseRepo, StyleRepo, StyleExampleRepo, StatsRepo, ReviewAnalysisRepo, HeadlineGenerationRepo
from ..db.schema import get_connection
from ..utils.text_stats import count_text_units
from ..utils import claude_client
from ..utils.claude_client import call as claude_call

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
UPLOAD_DIR = os.path.expanduser("~/Desktop/计算机/个人写作/data/uploads")
OBSIDIAN_VAULT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault")


def _extract_title(raw_content):
    """Extract a readable title from raw material content."""
    if not raw_content or not raw_content.strip():
        return ""
    lines = raw_content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        title = line.lstrip("#").strip()
        if title.startswith("=== ") or title.startswith("---"):
            continue
        if len(title) > 60:
            title = title[:60]
            last_space = title.rfind(" ")
            if last_space > 30:
                title = title[:last_space]
            title += "..."
        return title
    return ""


def _normalize_for_diff(text):
    """Normalize article text for rough equality checks."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _looks_effectively_unchanged(before, after):
    """Treat near-identical rewrite output as a failed modification."""
    before_norm = _normalize_for_diff(before)
    after_norm = _normalize_for_diff(after)
    if not before_norm or not after_norm:
        return False
    if before_norm == after_norm:
        return True
    ratio = difflib.SequenceMatcher(None, before_norm, after_norm).ratio()
    return ratio >= 0.985


def _split_sentences(text):
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*", text.replace("\r\n", "\n").replace("\r", "\n"))
    return [p.strip() for p in parts if p and p.strip()]


def _summarize_rewrite_changes(before, after, max_items=4):
    """Return a short user-facing summary of concrete rewrite changes."""
    before_sentences = _split_sentences(before)
    after_sentences = _split_sentences(after)
    if not before_sentences or not after_sentences:
        return []

    matcher = difflib.SequenceMatcher(a=before_sentences, b=after_sentences)
    items = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        before_chunk = "".join(before_sentences[i1:i2]).strip()
        after_chunk = "".join(after_sentences[j1:j2]).strip()
        if tag == "replace" and before_chunk and after_chunk:
            items.append(f"把\u201c{before_chunk[:36]}\u201d改成了\u201c{after_chunk[:36]}\u201d")
        elif tag == "delete" and before_chunk:
            items.append(f"删掉了\u201c{before_chunk[:36]}\u201d")
        elif tag == "insert" and after_chunk:
            items.append(f"新增了\u201c{after_chunk[:36]}\u201d")
        if len(items) >= max_items:
            break
    return items


def _flush_section(section_name, buffer, patterns_list, takeaways_list):
    """Flush a parsed section buffer into the appropriate output list."""
    text = "\n".join(buffer).strip()
    if not text:
        return
    if section_name == "patterns":
        patterns_list.append(text)


def _safe_image_name(name):
    base = os.path.basename(name or "pasted-image.png")
    base = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", base).strip("._")
    if not base:
        base = "pasted-image.png"
    if "." not in base:
        base += ".png"
    return base


def _safe_upload_name(name, fallback="uploaded-file"):
    base = os.path.basename(name or fallback)
    base = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", base).strip("._")
    return base or fallback


def _save_image_payloads(payloads):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    saved = []
    for item in payloads or []:
        data_url = item.get("dataUrl", "")
        if not data_url.startswith("data:image/"):
            continue
        try:
            header, b64 = data_url.split(",", 1)
            ext = header.split(";")[0].split("/")[-1].lower()
            if ext == "jpeg":
                ext = "jpg"
            name = _safe_image_name(item.get("name", f"image.{ext}"))
            if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                name += "." + ext
            filename = f"{uuid.uuid4().hex[:8]}-{name}"
            path = os.path.join(UPLOAD_DIR, filename)
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))
            saved.append({
                "name": item.get("name") or name,
                "marker": item.get("marker") or "",
                "path": path,
            })
        except Exception:
            continue
    return saved


def _decode_data_url(data_url):
    if not data_url or "," not in data_url:
        return b""
    return base64.b64decode(data_url.split(",", 1)[1])


def _extract_file_payloads(payloads):
    """Decode browser file payloads and turn supported binary files into text."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    parts = []
    for item in payloads or []:
        name = _safe_upload_name(item.get("name"), "uploaded-file")
        data_url = item.get("dataUrl", "")
        if not data_url:
            continue
        ext = os.path.splitext(name)[1].lower()
        try:
            raw = _decode_data_url(data_url)
            payload_dir = os.path.join(UPLOAD_DIR, uuid.uuid4().hex[:8])
            os.makedirs(payload_dir, exist_ok=True)
            path = os.path.join(payload_dir, name)
            with open(path, "wb") as f:
                f.write(raw)

            if ext in {".xlsx", ".xlsm", ".xls", ".csv"}:
                content, _ = read_spreadsheet(path)
            elif ext == ".epub":
                content, _ = read_epub(path)
            elif ext in {".txt", ".md", ".json", ".yml", ".yaml", ".csv", ".log"}:
                content = raw.decode("utf-8-sig", errors="replace")
            else:
                content = f"[已上传文件: {name}，保存位置: {path}。当前格式暂未自动解析。]"
            parts.append(f"## {name}\n\n{content}")
        except Exception as e:
            parts.append(f"## {name}\n\n[文件解析失败: {e}]")
    return "\n\n".join(parts)


def _find_obsidian_image(name):
    """Best-effort resolver for Obsidian wiki image embeds."""
    if not name:
        return ""
    candidates = []
    direct = os.path.expanduser(name)
    if os.path.isfile(direct):
        return direct
    roots = [OBSIDIAN_VAULT, os.getcwd()]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"node_modules", "__pycache__"}]
            if os.path.basename(name) in filenames:
                candidates.append(os.path.join(dirpath, os.path.basename(name)))
                break
        if candidates:
            return candidates[0]
    return ""


def _prepare_multimodal_markdown(text, image_payloads):
    """Preserve image/text order by replacing image placeholders with paths."""
    text = text or ""
    saved_images = _save_image_payloads(image_payloads)
    used = set()
    for img in saved_images:
        markdown = f"![{img['name']}]({img['path']})"
        marker = img.get("marker")
        if marker and marker in text:
            text = text.replace(marker, markdown)
            used.add(marker)

    def replace_obsidian_embed(match):
        inner = match.group(1).strip()
        # Leave already-handled browser paste markers alone if something missed.
        if inner.startswith("PW_IMAGE_"):
            return match.group(0)
        image_path = _find_obsidian_image(inner)
        if image_path:
            return f"![{inner}]({image_path})"
        return f"[图片占位：{inner}，未找到本地文件。请确认 Obsidian 附件路径可访问。]"

    text = re.sub(r"!\[\[([^\]]+\.(?:png|jpg|jpeg|webp|gif|heic|heif))\]\]", replace_obsidian_embed, text, flags=re.IGNORECASE)

    # If images were attached but their markers were not in the text, append
    # them explicitly rather than silently dropping them.
    leftovers = [img for img in saved_images if img.get("marker") not in used]
    if leftovers:
        text = text.rstrip() + "\n\n## 附加图片\n\n" + "\n\n".join(
            f"![{img['name']}]({img['path']})" for img in leftovers
        )
    return text


def create_app():
    """Create and configure the Flask app."""
    app = Flask(__name__, template_folder=TEMPLATE_DIR)

    pipeline.init()

    @app.template_filter("strip_md")
    def strip_md(text):
        """Strip Markdown formatting for plain-text display."""
        import re
        if not text:
            return ""
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Keep image markdown intact so image/text order survives editing.
        text = re.sub(r'(?<!!)\[([^\]]*)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @app.template_filter("word_count")
    def word_count(text):
        """Chinese-friendly word/character count for displayed articles."""
        return count_text_units(text)

    @app.context_processor
    def inject_sidebar():
        """Inject recent sessions for sidebar navigation."""
        try:
            sidebar_sessions = SessionRepo.list_recent(limit=12)
            for s in sidebar_sessions:
                mt = s.get("material_title") or _extract_title(s.get("material_content", ""))
                style_list = json.loads(s.get("style_names", "[]"))
                s["_style_display"] = ", ".join(style_list[:3])
                s["_material_preview"] = mt or (s.get("material_content", "")[:60].replace("\n", " "))
                s["_title"] = s.get("title") or mt or ("任务 #" + str(s["id"]))
            return dict(sidebar_sessions=sidebar_sessions)
        except Exception:
            return dict(sidebar_sessions=[])

    # ─── Page Routes ───

    @app.route("/", methods=["GET", "POST"])
    def write_page():
        styles = style_registry.list_info()
        results = None
        content = ""
        selected = []
        preselect = request.args.get("preselect", "")
        if preselect:
            selected.append(preselect)

        if request.method == "POST":
            content = request.form.get("content", "")
            attached_content = request.form.get("attached_content", "")
            try:
                image_payloads = json.loads(request.form.get("image_payloads", "[]") or "[]")
            except Exception:
                image_payloads = []
            try:
                file_payloads = json.loads(request.form.get("file_payloads", "[]") or "[]")
            except Exception:
                file_payloads = []
            file_path = request.form.get("file_path", "").strip()
            generation_mode = "fast"
            styles_str = request.form.get("styles", "")
            selected = [s.strip() for s in styles_str.split(",") if s.strip()]
            generation_parts = []
            if content.strip():
                generation_parts.append(content.strip())
            if attached_content.strip():
                generation_parts.append(attached_content.strip())
            extracted_files = _extract_file_payloads(file_payloads)
            if extracted_files.strip():
                generation_parts.append(extracted_files.strip())

            # If a local file path is provided, read it and prepend to content
            if file_path:
                try:
                    from ..core.input_reader import read_input as read_path
                    path_content, st, path_title = read_path(file_path)
                    if path_content:
                        generation_parts.insert(0, path_content.strip())
                except Exception as e:
                    generation_parts.insert(0, f"[读取路径失败: {e}]")

            generation_content = "\n\n---\n\n".join(p for p in generation_parts if p)
            generation_content = _prepare_multimodal_markdown(generation_content, image_payloads)
            if generation_content.strip():
                try:
                    result = pipeline.write(generation_content, selected, generation_mode=generation_mode)
                    results = result["articles"]
                except Exception as e:
                    results = [{"style": "error", "error": str(e), "title": "", "content": ""}]

        return render_template("write.html", styles=styles, selected=selected, content=content, results=results)

    @app.route("/history")
    def history_page():
        query = request.args.get("q", "").strip()
        if query:
            materials = MaterialRepo.search(query, limit=30)
        else:
            materials = MaterialRepo.list(limit=30)
        sessions_by_material = {}
        articles_by_session = {}
        for m in materials:
            if not m.get("title") or m["title"] == "":
                m["_display_title"] = _extract_title(m["raw_content"])
            else:
                m["_display_title"] = m["title"]
            if not m["_display_title"]:
                sessions = SessionRepo.list_by_material(m["id"])
                for s in sessions[:1]:
                    for a in ArticleRepo.list_by_session(s["id"]):
                        t = a.get("headline_selected") or a.get("title", "")
                        if t:
                            m["_display_title"] = t
                            break
                    if m["_display_title"]:
                        break
            sessions = SessionRepo.list_by_material(m["id"])
            sessions_by_material[m["id"]] = sessions
            for s in sessions:
                articles_by_session[s["id"]] = ArticleRepo.list_by_session(s["id"])
        return render_template("history.html", materials=materials, sessions_by_material=sessions_by_material, articles_by_session=articles_by_session, query=query)

    @app.route("/materials")
    def materials_page():
        query = request.args.get("q", "").strip()
        if query:
            materials = MaterialRepo.search(query, limit=50)
        else:
            materials = MaterialRepo.list(limit=50)
        for m in materials:
            if not m.get("title") or m["title"] == "":
                m["_display_title"] = _extract_title(m["raw_content"])
            else:
                m["_display_title"] = m["title"]
            if not m["_display_title"]:
                m["_display_title"] = f"素材 #{m['id']}"
        return render_template("materials.html", materials=materials, query=query)

    @app.route("/material/<int:material_id>")
    def material_detail_page(material_id):
        m = MaterialRepo.get(material_id)
        if not m:
            return "素材未找到", 404
        title = m.get("title") or _extract_title(m.get("raw_content", "")) or f"素材 #{m['id']}"
        sessions = SessionRepo.list_by_material(material_id)
        articles_by_session = {}
        for s in sessions:
            articles_by_session[s["id"]] = ArticleRepo.list_by_session(s["id"])
        return render_template("material_detail.html", material=m, title=title, sessions=sessions, articles_by_session=articles_by_session)

    @app.route("/styles")
    def styles_page():
        s = style_registry.list_info()
        return render_template("styles.html", styles=s)

    @app.route("/styles/<name>")
    def style_detail_page(name):
        style_obj = style_registry.get(name)
        if not style_obj:
            return "风格未找到", 404
        db_style = StyleRepo.get_by_name(name)
        if hasattr(style_obj, "get_prompt_template"):
            try:
                prompt = style_obj.get_prompt_template()
            except NotImplementedError:
                prompt = ""
        else:
            prompt = ""
        config = style_obj.get_config()
        prompt = config.get("prompt_template") or prompt
        examples = []
        if db_style:
            examples = StyleExampleRepo.list_by_style(db_style["id"])
        # Load orphaned examples (style_id that no longer exists in styles table)
        orphaned = []
        conn = get_connection()
        valid_ids = conn.execute("SELECT id FROM styles").fetchall()
        valid_ids_set = {r["id"] for r in valid_ids}
        all_examples = conn.execute("SELECT * FROM style_examples ORDER BY id DESC").fetchall()
        for ex in all_examples:
            if ex["style_id"] not in valid_ids_set:
                orphaned.append(dict(ex))
        conn.close()
        info = {
            "name": style_obj.name,
            "display_name": style_obj.display_name,
            "description": style_obj.description,
            "config": config,
            "is_builtin": db_style.get("is_builtin", 1) if db_style else True,
            "db_id": db_style["id"] if db_style else None,
            "prompt_template": prompt,
            "examples": examples,
            "orphaned_examples": orphaned,
        }
        return render_template("style_detail.html", style=info)

    @app.route("/stats")
    def stats_page():
        by_style = StatsRepo.articles_by_style()
        totals = StatsRepo.total_counts()
        by_day = StatsRepo.articles_by_day()
        return render_template("stats.html", by_style=by_style, totals=totals, by_day=by_day)

    @app.route("/review")
    def review_page():
        review_data = pipeline.generate_writing_review(limit=20)
        analysis_history = pipeline.get_review_analysis_history(limit=5)
        review_data["analysis_history"] = analysis_history
        return render_template("review.html", **review_data)

    @app.route("/headline", methods=["GET", "POST"])
    def headline_page():
        styles = style_registry.list_info()
        result = None
        content = ""
        selected_style = ""
        if request.method == "POST":
            content = request.form.get("content", "")
            selected_style = request.form.get("style", "")
            if content.strip():
                try:
                    result = pipeline.generate_headlines(content, selected_style or None)
                    # Save to generation history
                    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                    content_preview = content.strip()[:100].replace("\n", " ")
                    result_json = json.dumps([{"headline": h, "formula": f} for h, f in result], ensure_ascii=False)
                    HeadlineGenerationRepo.create(content_hash, content_preview, selected_style, result_json, content=content)
                except Exception as e:
                    result = f"出错: {e}"
        headline_library = HeadlineLibraryRepo.list(selected_style or "", limit=30)
        analyses_history = HeadlineAnalysisRepo.list(limit=10)
        # Load generation history: always show recent, plus content-specific if available
        generation_history = []
        recent = HeadlineGenerationRepo.list_recent(limit=8)
        for g in recent:
            try:
                g["_items"] = json.loads(g.get("result", "[]"))
            except Exception:
                g["_items"] = []
            generation_history.append(g)
        # For POST with content, also add content-specific history (avoid duplicates)
        if content.strip():
            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
            extra = HeadlineGenerationRepo.list_by_content_hash(content_hash, limit=5)
            seen_ids = {g["id"] for g in generation_history}
            for g in extra:
                if g["id"] not in seen_ids:
                    try:
                        g["_items"] = json.loads(g.get("result", "[]"))
                    except Exception:
                        g["_items"] = []
                    generation_history.append(g)
        return render_template("headline.html", styles=styles, content=content, selected_style=selected_style, result=result, headline_library=headline_library, analyses_history=analyses_history, generation_history=generation_history)

    @app.route("/settings")
    def settings_page():
        """设置页面：微信凭证配置。"""
        config_path = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/config.json")
        creds = {"app_id": "", "app_secret": "", "author": ""}
        if os.path.isfile(config_path):
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
                creds = cfg.get("wechat", creds)
        # Also read from .env
        env_path = os.path.expanduser("~/.openclaw/.env")
        env_creds = {}
        if os.path.isfile(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_creds[k.strip()] = v.strip().strip("'\"")
        if not creds["app_id"]:
            creds["app_id"] = env_creds.get("WECHAT_APP_ID", "")
        if not creds["app_secret"]:
            creds["app_secret"] = env_creds.get("WECHAT_APP_SECRET", "")
        if not creds["author"]:
            creds["author"] = env_creds.get("WECHAT_AUTHOR", "")
        return render_template("settings.html", creds=creds)

    @app.route("/session/<int:session_id>")
    def session_page(session_id):
        session = SessionRepo.get(session_id)
        if not session:
            return "未找到", 404
        material = MaterialRepo.get(session["material_id"])
        articles = ArticleRepo.list_by_session(session_id)
        for a in articles:
            # Add display_name from style registry
            style_obj = style_registry.get(a.get("style", ""))
            a["display_name"] = style_obj.display_name if style_obj else a.get("style", "")
            try:
                candidates_raw = a.get("headline_candidates", "[]")
                if isinstance(candidates_raw, str):
                    a["headline_candidates"] = json.loads(candidates_raw)
                else:
                    a["headline_candidates"] = candidates_raw or []
            except (json.JSONDecodeError, TypeError):
                a["headline_candidates"] = []
        return render_template("session.html", session=session, material=material, articles=articles)

    # ─── API Routes ───

    @app.route("/api/v1/styles")
    def api_styles():
        return jsonify(style_registry.list_info())

    @app.route("/api/v1/headlines/library", methods=["POST"])
    def api_add_headline_library():
        data = request.get_json()
        headlines_raw = data.get("headlines") if data else None
        if headlines_raw and isinstance(headlines_raw, list):
            # Batch add
            style = (data.get("style", "") if data else "").strip()
            note = (data.get("note", "") if data else "").strip()
            source = (data.get("source", "") if data else "").strip()
            added = 0
            for h in headlines_raw:
                h_text = (h or "").strip()
                if not h_text:
                    continue
                if len(h_text) > 120:
                    h_text = h_text[:120]
                HeadlineLibraryRepo.create(h_text, style, note, source)
                added += 1
            return jsonify({"status": "ok", "added": added})
        # Single add (backwards compatible)
        headline = (data.get("headline", "") if data else "").strip()
        if not headline:
            return jsonify({"status": "error", "message": "标题不能为空"}), 400
        if len(headline) > 120:
            headline = headline[:120]
        style = (data.get("style", "") if data else "").strip()
        note = (data.get("note", "") if data else "").strip()
        source = (data.get("source", "") if data else "").strip()
        item_id = HeadlineLibraryRepo.create(headline, style, note, source)
        return jsonify({"status": "ok", "id": item_id, "headline": headline})

    @app.route("/api/v1/headlines/library/batch-delete", methods=["POST"])
    def api_headline_library_batch_delete():
        """Delete multiple headline library items."""
        data = request.get_json()
        ids = data.get("ids", []) if data else []
        if not ids:
            return jsonify({"status": "error", "message": "No ids provided"}), 400
        HeadlineLibraryRepo.delete_batch(ids)
        return jsonify({"status": "ok", "deleted": len(ids)})

    @app.route("/api/v1/headlines/library/<int:item_id>", methods=["GET", "PATCH", "POST", "DELETE"])
    def api_headline_library_item(item_id):
        """Get, update, or delete a headline library item."""
        if request.method == "DELETE":
            HeadlineLibraryRepo.delete(item_id)
            return jsonify({"status": "ok"})
        elif request.method in ("PATCH", "POST"):
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "No data"}), 400
            headline = ((data.get("headline") or "") if data else "").strip()
            style = ((data.get("style") or "") if data else "").strip()
            note = ((data.get("note") or "") if data else "").strip()
            source = ((data.get("source") or "") if data else "").strip()
            HeadlineLibraryRepo.update(
                item_id,
                headline=headline or None,  # None = don't update
                style=style,
                note=note,
                source=source,
            )
            return jsonify({"status": "ok"})
        else:
            item = HeadlineLibraryRepo._get(item_id)
            if not item:
                return jsonify({"status": "error", "message": "Not found"}), 404
            return jsonify({"status": "ok", "item": item})

    @app.route("/api/v1/headlines/analyze", methods=["POST"])
    def api_analyze_headlines():
        """AI analysis of collected headline examples."""
        data = request.get_json() or {}
        style = (data.get("style", "") or "").strip()
        limit = data.get("limit", 10)

        # Fetch headlines to analyze
        headlines = HeadlineLibraryRepo.list(style=style, limit=limit)
        if not headlines:
            return jsonify({"status": "error", "message": "还没有积累标题，先添加一些标题再分析"}), 400

        headline_ids = [h["id"] for h in headlines]
        headlines_text = "\n".join(
            f"{i+1}. [{h.get('style') or '通用'}] {h['headline']}"
            for i, h in enumerate(headlines)
        )

        prompt = f"""你是一位标题分析专家。下面是我积累的标题范本，请对这些标题进行系统分析。

## 标题范本

{headlines_text}

## 分析要求

请从以下几个维度分析这些标题：

1. **总体概括（1-2句话）**：这批标题整体有什么共同特征？
2. **核心模式**：识别出 3-5 个重复出现的标题公式/结构模式
3. **写作技巧**：从这批标题中提炼 2-4 个具体可学的写作技巧（如用词选择、句式节奏、情绪调动等）
4. **积累建议**：基于当前标题库，建议还可以补充什么类型的标题，让积累更系统

在**核心模式**部分，请严格使用以下表格格式输出，不要用其他格式：

| 模式名称 | 公式 | 示例标题 |
|---|---|---|
| **痛点+解决方案** | `从0开始，用X做Y的教程来了` | #标题编号 |

每个模式一行，公式用反引号包裹。

请用中文输出，保持简洁直接。"""

        try:
            raw = claude_call(prompt)
            if not raw or not raw.strip():
                return jsonify({"status": "error", "message": "AI 分析返回为空，请重试"}), 502

            raw = raw.strip()

            # Parse structured analysis from the response using sections
            summary = ""
            patterns = []
            key_takeaways = []
            tips = ""

            lines = raw.split("\n")
            current_section = ""
            section_buffer = []

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("**1.") or stripped.startswith("1.") or "总体概括" in stripped:
                    current_section = "summary"
                    continue
                elif stripped.startswith("**2.") or stripped.startswith("2.") or "核心模式" in stripped:
                    if section_buffer:
                        _flush_section(current_section, section_buffer, patterns, key_takeaways)
                    current_section = "patterns"
                    section_buffer = []
                    continue
                elif stripped.startswith("**3.") or stripped.startswith("3.") or "写作技巧" in stripped:
                    if current_section == "patterns" and section_buffer:
                        _flush_section(current_section, section_buffer, patterns, key_takeaways)
                    current_section = "tips"
                    section_buffer = []
                    continue
                elif stripped.startswith("**4.") or stripped.startswith("4.") or "积累建议" in stripped:
                    current_section = "summary_extra"
                    section_buffer = []
                    continue

                if current_section == "summary":
                    summary = (summary + " " + stripped).strip()
                elif current_section == "patterns":
                    if stripped and not stripped.startswith("-") and not stripped.startswith("*"):
                        if section_buffer:
                            _flush_section(current_section, section_buffer, patterns, key_takeaways)
                            section_buffer = []
                    section_buffer.append(stripped)
                elif current_section == "tips":
                    section_buffer.append(stripped)
                elif current_section == "summary_extra":
                    section_buffer.append(stripped)

            # Flush remaining
            if current_section == "patterns" and section_buffer:
                _flush_section(current_section, section_buffer, patterns, key_takeaways)
            elif current_section == "tips" and section_buffer:
                tips = "\n".join(section_buffer).strip()
            elif current_section == "summary_extra" and section_buffer:
                extra = "\n".join(section_buffer).strip()
                if extra:
                    tips = (tips + "\n\n" + extra).strip()

            # If parsing didn't produce structured results, use the whole response
            if not summary and not patterns and not tips:
                # Try to extract patterns as bullet points
                for line in lines:
                    stripped = line.strip()
                    if stripped and (stripped.startswith("-") or stripped.startswith("*") or stripped[0].isdigit()):
                        if len(stripped) > 10:
                            patterns.append(stripped.lstrip("-*0123456789. ").strip())

                if patterns:
                    summary = raw[:200]
                else:
                    summary = raw

            analysis_id = HeadlineAnalysisRepo.create(
                style=style,
                headline_ids=headline_ids,
                headline_count=len(headlines),
                summary=summary,
                patterns=patterns,
                key_takeaways=key_takeaways,
                tips=tips,
                raw_analysis=raw,
            )

            # ─── Auto-save patterns as headline formulas ───
            saved_formulas = []
            for p in patterns:
                # Skip table separators
                if p.strip().startswith("|") and all(c in p for c in "|-"):
                    continue
                f_name = ""
                f_template = ""
                # Try markdown table: | **name** | `formula` ...
                table_m = re.match(r'\|\s*\*{0,2}\s*(.+?)\s*\*{0,2}\s*\|\s*`([^`]+)`', p)
                if table_m:
                    f_name = table_m.group(1).strip().strip('*"').strip('"')
                    f_template = table_m.group(2).strip()
                else:
                    # Try: "模式名称：xxx，公式：xxx"
                    name_match = re.match(r'^[：:\s]*(.+?)[，,]\s*(?:公式|模板)[：:]\s*(.+)', p)
                    if not name_match:
                        # Try: "**xxx**：公式"
                        name_match = re.match(r'[*]*\s*(.+?)[*]*\s*[：:]\s*(?:公式|模板)[：:]?\s*(.+)', p)
                    if name_match:
                        f_name = name_match.group(1).strip().strip('*"').strip('"').strip('「').strip('」')
                        f_template = name_match.group(2).strip().strip('*"').strip('"')
                if f_name and f_template and len(f_name) <= 50:
                    f_suitable = json.dumps([style] if style else ["daily", "sherry", "short_science", "xiaohongshu"])
                    f_desc = f"AI分析自动生成：{summary[:80]}"
                    f_example = ""
                    for h in headlines:
                        if any(kw in h["headline"] for kw in f_template.replace("XX", "").split()):
                            f_example = h["headline"]
                            break
                    inserted = HeadlineFormulaRepo.create(f_name, f_template, f_suitable, f_desc, f_example)
                    if inserted:
                        saved_formulas.append(f_name)

            return jsonify({
                "status": "ok",
                "analysis": {
                    "id": analysis_id,
                    "style": style,
                    "headline_count": len(headlines),
                    "summary": summary,
                    "patterns": patterns,
                    "key_takeaways": key_takeaways,
                    "tips": tips,
                    "raw_analysis": raw,
                    "created_at": "",
                    "saved_formulas": saved_formulas,
                }
            })
        except Exception as e:
            return jsonify({"status": "error", "message": f"分析失败: {str(e)}"}), 500

    @app.route("/api/v1/headlines/generate", methods=["POST"])
    def api_generate_headlines():
        """Generate headline candidates via AJAX (no page reload)."""
        data = request.get_json() or {}
        content = (data.get("content", "") or "").strip()
        style = (data.get("style", "") or "").strip()
        if not content:
            return jsonify({"status": "error", "message": "素材不能为空"}), 400
        try:
            result = pipeline.generate_headlines(content, style or None)
            # Save to generation history
            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
            content_preview = content[:100].replace("\n", " ")
            result_json = json.dumps([{"headline": h, "formula": f} for h, f in result], ensure_ascii=False)
            HeadlineGenerationRepo.create(content_hash, content_preview, style, result_json, content=content)
            return jsonify({"status": "ok", "candidates": [{"headline": h, "formula": f} for h, f in result]})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/v1/headlines/analysis", methods=["GET"])
    def api_list_headline_analysis():
        """List headline analysis history."""
        analyses = HeadlineAnalysisRepo.list(limit=10)
        return jsonify({"status": "ok", "analyses": analyses})

    @app.route("/api/v1/headlines/analysis/<int:analysis_id>", methods=["DELETE"])
    def api_delete_headline_analysis(analysis_id):
        HeadlineAnalysisRepo.delete(analysis_id)
        return jsonify({"status": "ok"})

    @app.route("/api/v1/generation/cancel", methods=["POST"])
    def api_cancel_generation():
        cancelled = claude_client.cancel_active_calls()
        return jsonify({"status": "ok", "cancelled": cancelled})

    @app.route("/api/v1/sessions/<int:session_id>/rename", methods=["POST"])
    def api_rename_session(session_id):
        session = SessionRepo.get(session_id)
        if not session:
            return jsonify({"status": "error", "message": "Session not found"}), 404
        data = request.get_json()
        title = (data.get("title", "") if data else "").strip()
        if not title:
            return jsonify({"status": "error", "message": "标题不能为空"}), 400
        if len(title) > 80:
            title = title[:80]
        SessionRepo.update_title(session_id, title)
        return jsonify({"status": "ok", "title": title})

    @app.route("/api/v1/sessions/<int:session_id>", methods=["DELETE"])
    def api_delete_session(session_id):
        session = SessionRepo.get(session_id)
        if not session:
            return jsonify({"status": "error", "message": "Session not found"}), 404
        SessionRepo.delete_with_material(session_id)
        return jsonify({"status": "ok"})

    @app.route("/api/v1/styles/create", methods=["POST"])
    def api_create_style():
        data = request.get_json()
        if not data or "name" not in data or "display_name" not in data:
            return jsonify({"status": "error", "message": "缺少 name 或 display_name"}), 400
        name = data["name"].strip().lower().replace(" ", "_")
        if StyleRepo.get_by_name(name):
            return jsonify({"status": "error", "message": "风格标识已存在"}), 400
        config = {"prompt_template": _sanitize_style_prompt_template(data.get("prompt_template", ""))}
        StyleRepo.create(name, data["display_name"], data.get("description", ""), config, is_builtin=0)
        style_registry.reload()
        return jsonify({"status": "ok"})

    @app.route("/api/v1/styles/draft-optimize", methods=["POST"])
    def api_optimize_draft_style():
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "缺少参数"}), 400
        display_name = (data.get("display_name", "") or "").strip()
        description = (data.get("description", "") or "").strip()
        current_prompt = (data.get("prompt_template", "") or "").strip()
        examples = data.get("examples", []) or []
        file_payloads = data.get("file_payloads", []) or []
        valid_examples = []
        for ex in examples:
            content = (ex.get("content", "") if isinstance(ex, dict) else "").strip()
            if not content:
                continue
            valid_examples.append({
                "title": (ex.get("title", "") if isinstance(ex, dict) else "").strip() or "无标题",
                "content": content,
                "source": (ex.get("source", "") if isinstance(ex, dict) else "").strip(),
            })
        extracted_files = _extract_file_payloads(file_payloads)
        if extracted_files.strip():
            valid_examples.append({
                "title": "上传文件解析结果",
                "content": extracted_files.strip(),
                "source": "uploaded_files",
            })
        if not valid_examples:
            return jsonify({"status": "error", "message": "请先粘贴参考素材"}), 400

        ref_parts = []
        for ex in valid_examples[:8]:
            ref_parts.append(f"--- {ex['title']}（{len(ex['content'])}字）---\n{ex['content'][:4000]}")
        ref_text = "\n\n".join(ref_parts)
        style_label = display_name or "新风格"
        seed_prompt = current_prompt or f"""# {style_label}写作风格

你正在模仿一种个人写作声音。先用 2-3 句话定义这个写作者是谁、在什么状态下写作、作品读起来像什么。

## 核心价值观

## 素材理解与选题判断

## 输出形态（文章/歌词/诗歌等）

## 语言风格

## 结构特征

## 具体细节的使用

## 情绪表达方式

## 节奏与段落

## 推荐表达

## 绝对禁区

## 输出要求
"""
        prompt = f"""你是一位写作风格 Skill 作者。你的任务不是总结改进点，而是基于参考素材，输出一份完整可直接用于写作生成的风格 prompt。

风格名称：{style_label}
补充描述：{description or "无"}

当前草稿 prompt：
{seed_prompt}

参考素材：
{ref_text}

请严格按下面骨架输出完整 prompt，保留所有标题：

# {style_label}写作风格

你正在模仿一种个人写作声音。先用 2-3 句话定义这个写作者是谁、在什么状态下写作、文章读起来像什么。

## 核心价值观

## 素材理解与选题判断

## 输出形态（文章/歌词/诗歌等）

## 语言风格

## 结构特征

## 具体细节的使用

## 情绪表达方式

## 节奏与段落

## 推荐表达

## 绝对禁区

## 输出要求

要求：
- 必须从参考素材里归纳，不要空泛。
- 直接输出完整 prompt，不要解释，不要写"主要改进点"。
- 不要创建文件。"""
        try:
            result = _sanitize_style_prompt_template(claude_call(prompt).strip())
            if len(result) > 14000:
                result = result[:14000].rstrip()
            return jsonify({"status": "ok", "prompt_template": result})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/v1/styles/<name>/update", methods=["POST"])
    def api_update_style_field(name):
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        data = request.get_json()
        if not data or "field" not in data:
            return jsonify({"status": "error", "message": "No field"}), 400
        field = data["field"]
        value = data["value"]
        if field in ("display_name", "description"):
            conn = get_connection()
            conn.execute(f"UPDATE styles SET {field} = ? WHERE name = ?", (value, name))
            conn.commit()
            conn.close()
        elif field in ("word_count", "tone", "structure", "personal_pronoun", "sentence_length", "paragraph_density", "humor_style", "ending_style"):
            config = json.loads(db_style["config"]) if isinstance(db_style["config"], str) else db_style.get("config", {})
            if field == "word_count":
                value = int(value)
            config[field] = value
            conn = get_connection()
            conn.execute("UPDATE styles SET config = ? WHERE name = ?", (json.dumps(config, ensure_ascii=False), name))
            conn.commit()
            conn.close()
        else:
            return jsonify({"status": "error", "message": f"Unknown field: {field}"}), 400
        return jsonify({"status": "ok"})

    @app.route("/api/v1/styles/<name>/delete", methods=["DELETE"])
    def api_delete_style(name):
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        if db_style.get("is_builtin"):
            return jsonify({"status": "error", "message": "内置风格不可删除"}), 400
        conn = get_connection()
        conn.execute("DELETE FROM styles WHERE name = ?", (name,))
        conn.commit()
        conn.close()
        style_registry.reload()
        return jsonify({"status": "ok"})

    @app.route("/api/v1/styles/<name>/config", methods=["POST"])
    def api_update_style_config(name):
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        data = request.get_json()
        if not data or "config" not in data:
            return jsonify({"status": "error", "message": "No config"}), 400
        current_config = json.loads(db_style["config"]) if isinstance(db_style["config"], str) else db_style.get("config", {})
        current_config.update(data["config"])
        conn = get_connection()
        conn.execute("UPDATE styles SET config = ? WHERE name = ?", (json.dumps(current_config, ensure_ascii=False), name))
        conn.commit()
        conn.close()
        style_registry.reload()
        return jsonify({"status": "ok"})

    @app.route("/api/v1/styles/<name>/prompt", methods=["POST"])
    def api_update_prompt(name):
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        data = request.get_json()
        if not data or "prompt_template" not in data:
            return jsonify({"status": "error", "message": "No prompt"}), 400
        config = json.loads(db_style["config"]) if isinstance(db_style["config"], str) else db_style.get("config", {})
        config["prompt_template"] = _sanitize_style_prompt_template(data["prompt_template"])
        conn = get_connection()
        conn.execute("UPDATE styles SET config = ? WHERE name = ?", (json.dumps(config, ensure_ascii=False), name))
        conn.commit()
        conn.close()
        style_registry.reload()
        return jsonify({"status": "ok"})

    @app.route("/api/v1/styles/<name>/optimize-prompt", methods=["POST"])
    def api_optimize_prompt(name):
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        examples = StyleExampleRepo.list_by_style(db_style["id"])
        if not examples:
            return jsonify({"status": "error", "message": "请先添加参考素材"}), 400
        refs = []
        for ex in examples:
            header = ex.get("title", "") or "无标题"
            refs.append(f"--- {header}（{len(ex['content'])}字）---\n{ex['content']}")
        ref_text = "\n\n".join(refs)
        config = json.loads(db_style["config"]) if isinstance(db_style["config"], str) else db_style.get("config", {})
        current_prompt = config.get("prompt_template", "")
        if not current_prompt:
            style_obj = style_registry.get(name)
            if style_obj:
                current_prompt = style_obj.get_prompt_template()
        required_sections = ("## 核心价值观", "## 输出形态", "## 语言风格", "## 绝对禁区", "## 输出要求")
        invalid_markers = ("主要改进点", "文件已保存", "已输出优化后的", "优化后的写作 prompt。", "已优化")

        def is_complete_prompt(text):
            return bool(text) and not any(marker in text for marker in invalid_markers) and all(section in text for section in required_sections)

        prompt = f"""你是一位写作风格 Skill 作者。你的任务不是总结改进点，而是重写一份完整的 `SKILL.md` 风格写作说明。

风格：{db_style['display_name']}
当前 prompt：{current_prompt}

参考文章：{ref_text}

请基于参考文章，在"当前 prompt"的基础上做增量优化，输出一份"完整可直接用于写作生成"的风格 prompt。

注意：
- 保留当前 prompt 已经写得好的规则。
- 从参考文章中补充新的具体观察。
- 不要只输出新增内容；必须输出合并后的完整 prompt。
- 不要只总结这次改了什么。

必须严格按下面骨架输出，保留所有一级/二级标题。每个二级标题下面至少写 3 条具体规则，必须从参考文章里归纳，不要泛泛而谈：

# {db_style['display_name']}写作风格

你正在模仿一种个人写作声音。先用 2-3 句话定义这个写作者是谁、在什么状态下写作、文章读起来像什么。

## 核心价值观

## 素材理解与选题判断

## 输出形态（文章/歌词/诗歌等）

## 语言风格

## 结构特征

## 具体细节的使用

## 情绪表达方式

## 节奏与段落

## 推荐表达

## 绝对禁区

## 输出要求

严禁：
- 不要输出"主要改进点"
- 不要输出"文件已保存"
- 不要输出"已优化"
- 不要输出总结、评价、说明或分析报告
- 不要只写摘要
- 不要写"已输出优化后的写作 prompt"
- 不要用编号列表解释你做了什么
- 不要创建文件

直接输出完整 prompt 正文。"""
        try:
            result = claude_call(prompt).strip()
            if len(result) > 12000:
                result = result[:12000].rstrip()
            if not is_complete_prompt(result):
                repair_prompt = f"""下面这个输出不是完整 prompt，不能直接使用。请把它修复成一份完整、可直接用于写作生成的风格 prompt。

原始当前 prompt：
{current_prompt}

模型刚才返回的不完整内容：
{result}

请严格按这个骨架输出完整 prompt，保留所有标题：

# {db_style['display_name']}写作风格

## 核心价值观
## 素材理解与选题判断
## 输出形态
## 语言风格
## 结构特征
## 具体细节的使用
## 情绪表达方式
## 节奏与段落
## 推荐表达
## 绝对禁区
## 输出要求

不要解释，不要总结，不要写"主要改进点"，直接输出完整 prompt。"""
                repaired = claude_call(repair_prompt).strip()
                if len(repaired) > 12000:
                    repaired = repaired[:12000].rstrip()
                if is_complete_prompt(repaired):
                    result = repaired
                else:
                    # Last resort: return a complete scaffold based on the current prompt,
                    # so the UI can still show a usable editable preview instead of failing.
                    result = f"""# {db_style['display_name']}写作风格

你正在模仿一种个人写作声音。以下规则基于已有 prompt 和参考文章继续整理，可在编辑框中继续微调。

## 核心价值观
{current_prompt}

## 素材理解与选题判断
- 先判断素材里真正有情绪、有细节、有转折的部分。
- 保留具体经历、地点、价格、时间、人物互动，不急着抽象总结。
- 如果素材只是零散记录，就把它整理成一条自然的个人观察线。

## 输出形态
{result}

## 语言风格
- 语言要具体、诚实、口语化。
- 少用宏大判断，多用真实细节。
- 句子长短交替，避免整齐划一。

## 结构特征
- 从一个具体场景、念头或困惑进入。
- 中间自然展开，不为了结构而结构。
- 结尾落在具体感受或画面上，不强行升华。

## 具体细节的使用
- 优先使用参考文章里的真实生活细节。
- 数字、地点、物件、动作要保留。
- 用细节表达情绪，少用抽象形容词。

## 情绪表达方式
- 情绪要诚实，但不要表演。
- 可以承认矛盾、遗憾、厌烦和喜欢。
- 不要为了积极而积极。

## 节奏与段落
- 一段只讲一个意思。
- 关键处可以用短句停顿。
- 段落之间要像自然想到下一件事。

## 推荐表达
- "其实"
- "不过"
- "话说回来"
- "我后来才发现"
- "这件事有点奇怪"

## 绝对禁区
- 不要输出 AI 解释、改动说明或写作分析。
- 不要使用"首先、其次、最后"。
- 不要强行升华。
- 不要用空泛套话。

## 输出要求
- 只输出文章正文。
- 不要解释，不要写修改说明。
- 不要创建文件，不要保存到磁盘。"""
            return jsonify({"status": "ok", "prompt_template": result})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/v1/styles/<name>/prompt/reset", methods=["POST"])
    def api_reset_prompt(name):
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        if not db_style.get("is_builtin"):
            return jsonify({"status": "error", "message": "自定义风格没有内置 Prompt 可恢复"}), 400
        config = json.loads(db_style["config"]) if isinstance(db_style["config"], str) else db_style.get("config", {})
        config.pop("prompt_template", None)
        conn = get_connection()
        conn.execute("UPDATE styles SET config = ? WHERE name = ?", (json.dumps(config, ensure_ascii=False), name))
        conn.commit()
        conn.close()
        style_registry.reload()
        style_obj = style_registry.get(name)
        prompt_template = style_obj.get_prompt_template() if style_obj else ""
        return jsonify({"status": "ok", "prompt_template": prompt_template})

    @app.route("/api/v1/styles/<name>/examples", methods=["GET"])
    def api_list_examples(name):
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        examples = StyleExampleRepo.list_by_style(db_style["id"])
        return jsonify({"status": "ok", "examples": examples})

    @app.route("/api/v1/styles/<name>/examples", methods=["POST"])
    def api_add_example(name):
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"status": "error", "message": "No content"}), 400
        ex_id = StyleExampleRepo.create(style_id=db_style["id"], title=data.get("title", ""), content=data["content"], source=data.get("source", ""))
        return jsonify({"status": "ok", "id": ex_id})

    @app.route("/api/v1/styles/examples/<int:example_id>", methods=["DELETE"])
    def api_delete_example(example_id):
        StyleExampleRepo.delete(example_id)
        return jsonify({"status": "ok"})

    @app.route("/api/v1/styles/<name>/examples/reclaim", methods=["POST"])
    def api_reclaim_examples(name):
        """Re-assign orphaned examples to this style."""
        db_style = StyleRepo.get_by_name(name)
        if not db_style:
            return jsonify({"status": "error", "message": "Style not found"}), 404
        data = request.get_json() or {}
        example_ids = data.get("example_ids", [])
        if not example_ids:
            return jsonify({"status": "error", "message": "No example IDs"}), 400
        conn = get_connection()
        # Verify these examples are actually orphaned
        valid_ids = {r["id"] for r in conn.execute("SELECT id FROM styles").fetchall()}
        reclaimed = 0
        for eid in example_ids:
            ex = conn.execute("SELECT * FROM style_examples WHERE id = ?", (eid,)).fetchone()
            if ex and ex["style_id"] not in valid_ids:
                conn.execute("UPDATE style_examples SET style_id = ? WHERE id = ?", (db_style["id"], eid))
                reclaimed += 1
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "reclaimed": reclaimed})

    @app.route("/api/v1/material/<int:material_id>", methods=["DELETE"])
    def api_delete_material(material_id):
        MaterialRepo.delete(material_id)
        return jsonify({"status": "ok"})

    @app.route("/api/v1/materials/bulk-delete", methods=["POST"])
    def api_bulk_delete_materials():
        data = request.get_json()
        ids = data.get("ids", []) if data else []
        deleted = 0
        for raw_id in ids:
            try:
                material_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            MaterialRepo.delete(material_id)
            deleted += 1
        return jsonify({"status": "ok", "deleted": deleted})

    @app.route("/api/v1/phrases", methods=["GET"])
    def api_list_phrases():
        cat = request.args.get("category", "")
        phrases = CommonPhraseRepo.list(category=cat) if cat else CommonPhraseRepo.list()
        return jsonify({"status": "ok", "phrases": phrases})

    @app.route("/api/v1/phrases", methods=["POST"])
    def api_add_phrase():
        data = request.get_json()
        if not data or "phrase" not in data:
            return jsonify({"status": "error", "message": "No phrase"}), 400
        pid = CommonPhraseRepo.create(data["phrase"], data.get("category", ""))
        return jsonify({"status": "ok", "id": pid})

    @app.route("/api/v1/phrases/<int:phrase_id>", methods=["DELETE"])
    def api_delete_phrase(phrase_id):
        CommonPhraseRepo.delete(phrase_id)
        return jsonify({"status": "ok"})

    @app.route("/api/v1/article/<int:article_id>/headlines")
    def api_get_headlines(article_id):
        a = ArticleRepo.get(article_id)
        if not a:
            return jsonify({"status": "error", "message": "Not found"}), 404
        try:
            candidates = json.loads(a.get("headline_candidates", "[]")) if isinstance(a.get("headline_candidates"), str) else a.get("headline_candidates", [])
        except Exception:
            candidates = []
        return jsonify({"status": "ok", "candidates": candidates, "selected": a.get("headline_selected", ""), "title": a.get("title", "")})

    @app.route("/api/v1/article/<int:article_id>/headline", methods=["POST"])
    @app.route("/api/v1/article/<int:article_id>/select-headline", methods=["POST"])
    def api_select_headline(article_id):
        data = request.get_json()
        if not data or "headline" not in data:
            return jsonify({"status": "error", "message": "No headline"}), 400
        headline = data["headline"]
        formula = data.get("formula", "")
        is_custom = 1 if data.get("is_custom") else 0
        article = ArticleRepo.get(article_id)
        if not article:
            return jsonify({"status": "error", "message": "Not found"}), 404
        session = SessionRepo.get(article["session_id"]) if article else None
        if headline:
            HeadlineFeedbackRepo.record(article_id=article_id, headline=headline, formula_name=formula, was_selected=1, is_custom=is_custom, material_id=session["material_id"] if session else 0, style=article.get("style", ""))
        ArticleRepo.select_headline(article_id, headline)
        return jsonify({"status": "ok"})

    def _apply_request_headline(article_id, data):
        """Persist a headline passed with archive/typeset/publish payloads."""
        if not data or "headline" not in data:
            return
        headline = (data.get("headline") or "").strip()
        if headline:
            ArticleRepo.select_headline(article_id, headline)

    def _article_title(article):
        return article.get("headline_selected") or article.get("title") or article.get("original_title") or "无标题"

    def _save_article_content(article_id, content):
        article = ArticleRepo.get(article_id)
        if not article:
            return False
        content = _clean_output(content)
        conn = get_connection()
        conn.execute(
            """
            UPDATE articles
            SET previous_content = content,
                content = ?,
                original_content = COALESCE(NULLIF(original_content, ''), content)
            WHERE id = ?
            """,
            (content, article_id),
        )
        conn.commit()
        conn.close()
        return True

    @app.route("/api/v1/article/<int:article_id>/content", methods=["POST"])
    @app.route("/api/v1/article/<int:article_id>/save", methods=["POST"])
    def api_save_content(article_id):
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"status": "error", "message": "No content"}), 400
        _apply_request_headline(article_id, data)
        ok = _save_article_content(article_id, data["content"])
        if not ok:
            return jsonify({"status": "error", "message": "Not found"}), 404
        return jsonify({"status": "ok"})

    @app.route("/api/v1/article/<int:article_id>/restore", methods=["POST"])
    def api_restore_article(article_id):
        article = ArticleRepo.get(article_id)
        if not article:
            return jsonify({"status": "error", "message": "Not found"}), 404
        data = request.get_json() or {}
        mode = data.get("mode", "previous")
        if mode == "original":
            target = article.get("original_content") or ""
            if not target:
                return jsonify({"status": "error", "message": "没有可恢复的原文"}), 400
        else:
            target = article.get("previous_content") or article.get("original_content") or ""
            if not target:
                return jsonify({"status": "error", "message": "没有可恢复的上一版"}), 400
        target = _clean_output(target)
        conn = get_connection()
        conn.execute(
            "UPDATE articles SET previous_content = content, content = ? WHERE id = ?",
            (target, article_id),
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "content": target})

    @app.route("/api/v1/article/<int:article_id>/archive", methods=["POST"])
    def api_archive_article(article_id):
        article = ArticleRepo.get(article_id)
        if not article:
            return jsonify({"status": "error", "message": "Not found"}), 404
        data = request.get_json()
        _apply_request_headline(article_id, data)
        content = data.get("content", "") if data else ""
        if not content:
            content = article["content"]
        # Clean AI preamble before archiving
        content = _clean_output(content)
        _save_article_content(article_id, content)
        article = ArticleRepo.get(article_id) or article
        title = _article_title(article)
        try:
            path = archive_to_works(content, title, article.get("style", ""))
            ArticleRepo.set_output_path(article_id, path)
            return jsonify({"status": "ok", "path": path})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    SAVE_DIR = os.path.expanduser("~/WorkBuddy/wechat-typeset-pro")

    def _enhance_markdown(content, title):
        """Preprocess Markdown to improve typeset quality — mirrors skill workflow steps 1.5+2."""
        import re
        md = f"# {title}\n\n{content}"
        md = re.sub(r'(?<=\S)\n(?=\S)', '\n\n', md)
        md = re.sub(r'\n{3,}', '\n\n', md)
        lines = [l.strip() for l in md.split('\n')]
        md = '\n'.join(lines)
        footer_markers = ['感谢阅读', '如果对你有帮助', '欢迎点赞', '关注公众号']
        has_footer = any(m in md[-200:] for m in footer_markers)
        if not has_footer:
            md += (
                '\n\n---\n\n'
                '<font color="#808080"><i>感谢阅读。如果对你有帮助，欢迎点赞收藏转发。</i></font>\n'
                '<font color="#808080"><i>关注公众号律海流深，获取更多 AI 实操经验。</i></font>'
            )
        return md

    def _typeset_gallery(content, title):
        """Run the full skill gallery workflow: save .md → format.py --gallery → return gallery HTML.

        Returns (gallery_html: str, md_path: str).
        """
        import re
        md_content = _enhance_markdown(content, title)
        # Sanitize filename
        safe_title = re.sub(r'[^\w\u4e00-\u9fff-]', '_', title)[:40]
        fname = f"web_{safe_title}.md"
        md_path = os.path.join(SAVE_DIR, fname)
        os.makedirs(SAVE_DIR, exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        format_script = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/scripts/format.py")
        if not os.path.isfile(format_script):
            raise FileNotFoundError("排版工具未找到")

        result = subprocess.run(
            ["python3", format_script, "--input", md_path, "--gallery", "--no-open"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:500] if result.stderr else str(result))

        # Read gallery.html
        file_stem = re.sub(r"-(公众号|小红书|微博)$", "", os.path.splitext(fname)[0])
        gallery_dir = os.path.join(SAVE_DIR, file_stem)
        gallery_path = os.path.join(gallery_dir, "gallery.html")
        if not os.path.isfile(gallery_path):
            raise FileNotFoundError(f"画廊页面未生成: {gallery_path}")

        with open(gallery_path, "r", encoding="utf-8") as f:
            gallery_html = f.read()

        return gallery_html, md_path, gallery_dir

    @app.route("/api/v1/article/<int:article_id>/typeset", methods=["POST"])
    def api_typeset_article(article_id):
        """排版：运行 skill gallery 模式，打开主题画廊供选择。"""
        article = ArticleRepo.get(article_id)
        if not article:
            return jsonify({"status": "error", "message": "Not found"}), 404
        data = request.get_json()
        _apply_request_headline(article_id, data)
        content = data.get("content", "") if data else ""
        if not content:
            content = article["content"]
        article = ArticleRepo.get(article_id) or article
        title = _article_title(article)
        content = _clean_output(content)

        try:
            gallery_html, md_path, gallery_dir = _typeset_gallery(content, title)
            if not gallery_html:
                return jsonify({"status": "error", "message": "画廊未生成"}), 500
            return jsonify({
                "status": "ok",
                "html": gallery_html,
                "article_dir": gallery_dir,
                "md_path": md_path,
            })
        except subprocess.TimeoutExpired:
            return jsonify({"status": "error", "message": "排版超时"}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/v1/article/<int:article_id>/publish", methods=["POST"])
    def api_publish_article(article_id):
        """发布到公众号：先按选中主题排版，再推送草稿箱。"""
        article = ArticleRepo.get(article_id)
        if not article:
            return jsonify({"status": "error", "message": "Not found"}), 404
        data = request.get_json()
        _apply_request_headline(article_id, data)
        content = data.get("content", "") if data else ""
        if not content:
            content = article["content"]
        theme = (data or {}).get("theme", "terracotta")
        article = ArticleRepo.get(article_id) or article
        title = _article_title(article)
        content = _clean_output(content)

        # 1. Format with chosen theme
        try:
            md_content = _enhance_markdown(content, title)
            import re
            safe_title = re.sub(r'[^\w\u4e00-\u9fff-]', '_', title)[:40]
            fname = f"pub_{safe_title}.md"
            md_path = os.path.join(SAVE_DIR, fname)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            format_script = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/scripts/format.py")
            result = subprocess.run(
                ["python3", format_script, "--input", md_path, "--theme", theme, "--no-open"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:500] if result.stderr else str(result))
        except subprocess.TimeoutExpired:
            return jsonify({"status": "error", "message": "排版超时"}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": f"排版失败: {e}"}), 500

        # 2. Push to WeChat draft
        file_stem = re.sub(r"-(公众号|小红书|微博)$", "", os.path.splitext(fname)[0])
        article_dir = os.path.join(SAVE_DIR, file_stem)
        publish_script = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/scripts/publish.py")
        if not os.path.isfile(publish_script):
            return jsonify({"status": "error", "message": "发布工具未找到"}), 500

        default_cover = os.path.expanduser(
            "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"
            "/我的作品/图片素材/公众号封面（没有指定封面就用这张）.png"
        )
        cmd = ["python3", publish_script, "--dir", article_dir]
        if os.path.isfile(default_cover):
            cmd += ["--cover", default_cover]

        try:
            pub_result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if pub_result.returncode != 0:
                raise RuntimeError(pub_result.stderr[:500] if pub_result.stderr else str(pub_result))
            return jsonify({
                "status": "ok",
                "output": pub_result.stdout[:3000],
            })
        except subprocess.TimeoutExpired:
            return jsonify({"status": "error", "message": "发布超时"}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/v1/article/<int:article_id>/rewrite", methods=["POST"])
    def api_rewrite_article(article_id):
        article = ArticleRepo.get(article_id)
        if not article:
            return jsonify({"status": "error", "message": "Not found"}), 404
        data = request.get_json()
        if not data or "instruction" not in data:
            return jsonify({"status": "error", "message": "No instruction"}), 400
        instruction = data["instruction"]
        current_content = data.get("content", "") or article["content"]
        style_name = article.get("style", "")
        style_obj = style_registry.get(style_name) if style_name else None
        style_config = style_obj.get_config() if style_obj else {}
        style_prompt = ""
        if style_obj and hasattr(style_obj, "get_prompt_template"):
            style_prompt = style_config.get("prompt_template") or style_obj.get_prompt_template()
        format_rules = _format_rules_for_style(style_name, style_config.get("output_form", "auto"))
        style_guardrails = DAILY_FINAL_GUARDRAILS if style_name == "daily" else ""
        rewrite_prompt = f"""我需要对下面这篇文章进行修改。

当前文章风格：{style_name or "未指定"}

当前风格规则
{style_prompt}

{style_guardrails}

当前文章内容
{current_content[:12000]}

修改要求
{instruction}

{STRICT_OUTPUT_RULES}
{HARD_CONSTRAINT_REPAIR_RULES}

## 修改时的硬性要求
- 严格保留用户真正要表达的对象，不要偷换概念。比如用户说的是"香港的菜/食物"，就不要改成"香港这座城市"。
- 修改只作用于文章内容本身，不要追加"主要改动""修改说明""表格""原文/修改/原因"。
- 必须真正落实"修改要求"，不能只润色原文后原样返回。
- 如果用户要求补入新的原因、新的判断、新的情绪立场，这些内容必须明确写进正文。
- 修改后的正文必须和当前版本有可见差异；如果几乎没改，说明这次修改失败，需要重写。
{format_rules}

        直接输出修改后的完整文章，不要解释，不要创建文件。"""
        try:
            raw_result = claude_call(rewrite_prompt)
            raw_result = raw_result.strip() if raw_result else ""
            result = _clean_output(raw_result) if raw_result else ""
            if style_name == "daily":
                result = _strip_daily_headings(result)
            result = _hard_enforce_output(result, rewrite_prompt, style_name)
            if (
                not result
                or looks_like_edit_report(raw_result)
                or looks_like_edit_report(result)
                or _looks_effectively_unchanged(current_content, result)
            ):
                retry_prompt = f"""{rewrite_prompt}

上一次输出有问题。请重新输出：
- 只输出修改后的完整正文。
- 第一行就进入文章内容。
- 不要写"已在对话中输出""主要处理了""主要改动""修改说明"。
- 不要列表说明你改了哪里。
- 不要基本照抄原文。
- 必须把"修改要求"里的新增信息和新增态度真正写进文章。"""
                raw_result = claude_call(retry_prompt)
                raw_result = raw_result.strip() if raw_result else ""
                result = _clean_output(raw_result) if raw_result else ""
                if style_name == "daily":
                    result = _strip_daily_headings(result)
                result = _hard_enforce_output(result, retry_prompt, style_name)
            if (
                not result
                or looks_like_edit_report(raw_result)
                or looks_like_edit_report(result)
                or _looks_effectively_unchanged(current_content, result)
            ):
                return jsonify({
                    "status": "error",
                    "message": "这次修改没有真正落实到正文里，系统已经拦截，原文没有被覆盖。请再试一次。"
                }), 502
            # Save original if first edit
            if not article.get("original_content"):
                conn = get_connection()
                conn.execute("UPDATE articles SET original_content = content WHERE id = ? AND (original_content IS NULL OR original_content = '')", (article_id,))
                conn.commit()
                conn.close()
            return jsonify({
                "status": "ok",
                "content": result,
                "instruction": instruction,
                "change_summary": _summarize_rewrite_changes(current_content, result),
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/v1/article/<int:article_id>/review", methods=["POST"])
    def api_review_article(article_id):
        article = ArticleRepo.get(article_id)
        if not article:
            return jsonify({"status": "error", "message": "Not found"}), 404
        data = request.get_json()
        current = data.get("content", "") if data else ""
        if not current:
            current = article["content"]
        original = article.get("original_content") or article["content"]
        if original == current:
            return jsonify({"status": "ok", "has_changes": False, "review": "内容未修改。"})
        review_prompt = f"""对比以下文章的原始版本和修改版本，给出修改反馈。

原始版本
{original[:3000]}

修改版本
{current[:3000]}

请输出：
1. 修改要点
2. 改进建议"""
        try:
            result = claude_call(review_prompt)
            return jsonify({"status": "ok", "has_changes": True, "review": result})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/v1/review/generate", methods=["POST"])
    def api_generate_review():
        try:
            review_data = pipeline.generate_writing_review(limit=20)
            return jsonify({"status": "ok", "analysis": review_data.get("analysis", ""), "count": review_data.get("count", 0)})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/v1/settings/wechat", methods=["POST"])
    def api_save_wechat_creds():
        """Save WeChat credentials and verify them."""
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        app_id = (data.get("app_id") or "").strip()
        app_secret = (data.get("app_secret") or "").strip()
        author = (data.get("author") or "").strip()

        if not app_id or not app_secret:
            return jsonify({"status": "error", "message": "APPID 和 AppSecret 不能为空"}), 400

        # Save to config.json
        skill_config = os.path.expanduser("~/.claude/skills/wechat-typeset-pro/config.json")
        if os.path.isfile(skill_config):
            with open(skill_config, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("wechat", {})["app_id"] = app_id
            cfg.setdefault("wechat", {})["app_secret"] = app_secret
            if author:
                cfg["wechat"]["author"] = author
            with open(skill_config, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

        # Save to ~/.openclaw/.env (publish.py reads this)
        openclaw_dir = os.path.expanduser("~/.openclaw")
        os.makedirs(openclaw_dir, exist_ok=True)
        env_path = os.path.join(openclaw_dir, ".env")

        # Read existing, update keys
        env_lines = {}
        if os.path.isfile(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        env_lines[k.strip()] = v.strip()
        env_lines["WECHAT_APP_ID"] = app_id
        env_lines["WECHAT_APP_SECRET"] = app_secret
        if author:
            env_lines["WECHAT_AUTHOR"] = author

        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in env_lines.items():
                f.write(f'{k}="{v}"\n')

        # Verify: try to get access_token
        import urllib.request
        import urllib.error
        verify_url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}"
        try:
            req = urllib.request.Request(verify_url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if "access_token" in result:
                return jsonify({"status": "ok", "message": "✅ 凭证有效，验证通过"})
            else:
                err = result.get("errmsg", str(result))
                return jsonify({"status": "ok", "warning": True, "message": f"⚠️ 已保存但验证失败: {err}"})
        except Exception as e:
            return jsonify({"status": "ok", "warning": True, "message": f"⚠️ 已保存但无法验证（网络错误）: {str(e)}"})

    return app
