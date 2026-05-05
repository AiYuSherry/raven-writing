"""CLI entry point for Personal Writing."""

import sys
import argparse
from ..core import pipeline
from ..core.style_engine import registry as style_registry
from ..db.repository import MaterialRepo, SessionRepo, ArticleRepo
from ..zotero_library import (
    build_reference_pack,
    build_writing_snippet,
    export_references,
    import_file,
    import_pdf_file,
    search_references,
)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Personal Writing — 个人写作工作平台",
        prog="personal-writing",
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # write command
    write_p = sub.add_parser("write", help="写文章")
    write_p.add_argument("input", nargs="?", default="", help="素材内容、文件路径或URL")
    write_p.add_argument("--style", "-s", action="append", dest="styles",
                        help="指定风格（可多次使用，如 -s daily -s sherry）")
    write_p.add_argument("--file", "-f", help="从文件读入素材")
    write_p.add_argument("--from-obsidian", help="从Obsidian取素材")
    write_p.add_argument("--research", "-r", action="store_true",
                        help="先研究再写作，输入作为问题而非素材")

    # list command
    list_p = sub.add_parser("list", help="查看历史")
    list_p.add_argument("--limit", "-n", type=int, default=10, help="条数")
    list_p.add_argument("--session", type=int, help="查看指定session的详情")

    # styles command
    sub.add_parser("styles", help="查看可用风格")

    # headline command
    headline_p = sub.add_parser("headline", help="生成标题候选")
    headline_p.add_argument("input", nargs="?", default="", help="素材内容")
    headline_p.add_argument("--file", "-f", help="从文件读入素材")
    headline_p.add_argument("--style", "-s", default="", help="指定风格筛选公式")

    # web command
    web_p = sub.add_parser("web", help="启动Web界面")
    web_p.add_argument("--port", "-p", type=int, default=5555, help="端口号（默认5555）")

    # init command
    sub.add_parser("init", help="初始化数据库")

    # zotero import/search helpers
    zotero_import_p = sub.add_parser("zotero-import", help="导入 Zotero/Better BibTeX 导出的文献")
    zotero_import_p.add_argument("--library-id", type=int, required=True, help="目标素材库 ID")
    zotero_import_p.add_argument("--file", required=True, help="BibTeX / CSL JSON / RIS 文件路径")
    zotero_import_p.add_argument("--format", default="", help="bibtex / csl-json / ris；不填自动识别")
    zotero_import_p.add_argument("--folder-id", default="", help="可选：导入到指定素材库文件夹")

    zotero_pdf_p = sub.add_parser("zotero-import-pdf", help="导入 PDF 为 Zotero-style 文献条目")
    zotero_pdf_p.add_argument("--library-id", type=int, required=True, help="目标素材库 ID")
    zotero_pdf_p.add_argument("--file", required=True, help="PDF 文件路径")
    zotero_pdf_p.add_argument("--folder-id", default="", help="可选：导入到指定素材库文件夹")
    zotero_pdf_p.add_argument("--title", default="", help="可选：覆盖自动提取的题名")
    zotero_pdf_p.add_argument("--authors", default="", help="可选：作者，多个作者用分号分隔")
    zotero_pdf_p.add_argument("--year", default="", help="可选：年份")
    zotero_pdf_p.add_argument("--journal", default="", help="可选：期刊/出版物")
    zotero_pdf_p.add_argument("--tags", default="", help="可选：标签，逗号或分号分隔")

    zotero_search_p = sub.add_parser("zotero-search", help="筛选 Zotero-style 文献")
    zotero_search_p.add_argument("--library-id", type=int, required=True, help="素材库 ID")
    zotero_search_p.add_argument("--query", "-q", default="", help="关键词")
    zotero_search_p.add_argument("--author", default="", help="作者")
    zotero_search_p.add_argument("--year", default="", help="年份")
    zotero_search_p.add_argument("--tag", default="", help="标签")
    zotero_search_p.add_argument("--journal", default="", help="期刊/出版物")
    zotero_search_p.add_argument("--limit", type=int, default=20, help="返回数量")

    zotero_snippet_p = sub.add_parser("zotero-snippet", help="生成可复制引用素材片段")
    zotero_snippet_p.add_argument("--document-id", type=int, required=True, help="Zotero 文献对应的 document_id")
    zotero_snippet_p.add_argument("--style", default="chinese", choices=["chinese", "apa"], help="引用格式")

    zotero_pack_p = sub.add_parser("zotero-reference-pack", help="生成 AI 写作参考文献包")
    zotero_pack_p.add_argument("--library-id", type=int, action="append", required=True, help="素材库 ID，可重复")
    zotero_pack_p.add_argument("--query", "-q", required=True, help="检索问题")
    zotero_pack_p.add_argument("--top-k", type=int, default=6, help="文献卡数量")
    zotero_pack_p.add_argument("--style", default="chinese", choices=["chinese", "apa"], help="引用格式")

    zotero_export_p = sub.add_parser("zotero-export", help="导出 Zotero-style 文献")
    zotero_export_p.add_argument("--library-id", type=int, required=True, help="素材库 ID")
    zotero_export_p.add_argument("--format", default="csl-json", choices=["csl-json", "bibtex"], help="导出格式")

    args = parser.parse_args()

    # Initialize
    pipeline.init()

    if args.command == "init":
        print("✅ 数据库初始化完成")
        return

    elif args.command == "write":
        cmd_write(args)

    elif args.command == "list":
        cmd_list(args)

    elif args.command == "styles":
        cmd_styles()

    elif args.command == "headline":
        cmd_headline(args)

    elif args.command == "web":
        cmd_web(args)

    elif args.command == "zotero-import":
        cmd_zotero_import(args)

    elif args.command == "zotero-import-pdf":
        cmd_zotero_import_pdf(args)

    elif args.command == "zotero-search":
        cmd_zotero_search(args)

    elif args.command == "zotero-snippet":
        cmd_zotero_snippet(args)

    elif args.command == "zotero-reference-pack":
        cmd_zotero_reference_pack(args)

    elif args.command == "zotero-export":
        cmd_zotero_export(args)

    else:
        parser.print_help()


def cmd_write(args):
    """Handle 'write' command."""
    # Determine input
    raw_input = args.input or ""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw_input = f.read()
    if args.from_obsidian:
        raw_input = f"@obsidian {args.from_obsidian}"

    if not raw_input.strip():
        # Interactive mode: read from stdin
        print("📝 请输入素材内容（Ctrl+D 结束）：")
        raw_input = sys.stdin.read().strip()
        if not raw_input:
            print("❌ 没有输入内容")
            return

    # Get styles
    style_names = args.styles
    available = [s["name"] for s in style_registry.list_info()]
    if style_names:
        for s in style_names:
            if s not in available:
                print(f"⚠️  未知风格: {s}，可用: {', '.join(available)}")
                return
    else:
        # Default: generate all styles
        style_names = available

    # Research mode: if --research, first research the topic
    if args.research:
        print(f"🔍 正在研究: {raw_input[:100]}...")
        research_prompt = f"""请针对以下主题/问题进行系统性研究，输出一份结构化的研究简报。

## 研究方法（基于横纵分析法）
1. **纵向分析**：该主题的发展历程、关键事件、演变脉络
2. **横向分析**：当前格局、主要参与者/竞品对比、行业位置
3. **核心发现**：关键事实、数据、论据
4. **写作素材**：值得展开的角度、可以引用的例子、独特洞察

## 研究主题
{raw_input}

## 输出要求
以研究简报形式输出，结构清晰、事实准确、适合作为写作素材。不要额外解释。"""
        from ..utils.claude_client import call as claude_call
        material = claude_call(research_prompt)
        raw_input = material
        print("✅ 研究完成，开始写作...")

    print(f"🚀 正在写作（风格: {', '.join(style_names)}）...")

    try:
        result = pipeline.write(raw_input, style_names)
    except Exception as e:
        print(f"❌ 出错: {e}")
        return

    print(f"\n✅ 完成！素材 #{result['material_id']}，批次 #{result['session_id']}")
    print()

    for article in result["articles"]:
        error = article.get("error")
        if error:
            print(f"  ⚠️  {article['style']}: {error}")
            continue

        print(f"─── {article['style']} ───")
        if article.get("title"):
            print(f"📎 {article['title']}")
        print()
        # Show first 300 chars
        content = article.get("content", "")
        preview = content[:300]
        if len(content) > 300:
            preview += "..."
        print(preview)
        print()


def cmd_list(args):
    """Handle 'list' command."""
    if args.session:
        session = SessionRepo.get(args.session)
        if not session:
            print(f"❌ 未找到批次 #{args.session}")
            return
        articles = ArticleRepo.list_by_session(args.session)
        print(f"批次 #{session['id']} — 素材 #{session['material_id']}")
        print(f"风格: {session['style_names']}")
        print(f"时间: {session['created_at']}")
        print()
        for a in articles:
            preview = a["content"][:200] + "..." if len(a["content"]) > 200 else a["content"]
            print(f"─── {a['style']} ───")
            print(f"📎 {a['title'] or '(无标题)'}")
            print(preview)
            print()
    else:
        materials = MaterialRepo.list(limit=args.limit)
        if not materials:
            print("暂无记录")
            return
        print(f"最近 {len(materials)} 条素材：")
        for m in materials:
            preview = m["raw_content"][:60].replace("\n", " ")
            print(f"  #{m['id']} [{m['source_type']}] {m['created_at']}")
            print(f"     {preview}...")


def cmd_styles():
    """Handle 'styles' command."""
    styles = style_registry.list_info()
    if not styles:
        print("暂无可用风格")
        return
    print("可用风格：")
    for s in styles:
        cfg = s.get("config", {})
        wc = cfg.get("word_count", "?")
        print(f"  {s['display_name']} ({s['name']})")
        print(f"     {s['description']}")
        print(f"     字数: ~{wc}")
        print()


def cmd_headline(args):
    """Handle 'headline' command."""
    raw_input = args.input or ""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw_input = f.read()
    if not raw_input.strip():
        print("📝 请输入素材内容（Ctrl+D 结束）：")
        raw_input = sys.stdin.read().strip()
        if not raw_input:
            print("❌ 没有输入内容")
            return

    print("🚀 正在生成标题...")
    result = pipeline.generate_headlines(raw_input, args.style or None)
    print()
    print(result)


def cmd_zotero_import(args):
    """Import a BibTeX/CSL JSON export into a material library."""
    try:
        imported = import_file(
            args.library_id,
            args.file,
            fmt=args.format,
            folder_id=args.folder_id,
        )
    except Exception as e:
        print(f"❌ Zotero 导入失败: {e}")
        return
    print(f"✅ 已导入 {len(imported)} 条 Zotero-style 文献")
    for item in imported[:20]:
        print(f"  document_id={item['document_id']} · {item.get('year') or 'n.d.'} · {item.get('title')}")


def cmd_zotero_import_pdf(args):
    """Import a PDF as a Zotero-style reference and indexed material."""
    try:
        imported = import_pdf_file(
            args.library_id,
            args.file,
            folder_id=args.folder_id,
            metadata={
                "title": args.title,
                "authors": args.authors,
                "year": args.year,
                "journal": args.journal,
                "tags": args.tags,
            },
        )
    except Exception as e:
        print(f"❌ PDF 文献导入失败: {e}")
        return
    print("✅ 已导入 PDF 文献")
    print(f"  document_id={imported['document_id']} · chunks={imported['chunk_count']}")
    print(f"  title={imported['title']}")
    print(f"  file={imported['file_path']}")


def cmd_zotero_search(args):
    """Search imported Zotero-style references."""
    refs = search_references(
        args.library_id,
        query=args.query,
        author=args.author,
        year=args.year,
        tag=args.tag,
        journal=args.journal,
        limit=args.limit,
    )
    if not refs:
        print("没有匹配文献")
        return
    for ref in refs:
        authors = "；".join(ref.get("authors") or []) or "佚名"
        print(f"document_id={ref['document_id']} · {authors} · {ref.get('year') or 'n.d.'}")
        print(f"  {ref.get('title')}")
        if ref.get("publicationTitle"):
            print(f"  {ref.get('publicationTitle')}")


def cmd_zotero_snippet(args):
    """Print a copyable writing-desk citation/material snippet."""
    snippet = build_writing_snippet(args.document_id, citation_style=args.style)
    if not snippet:
        print("未找到 Zotero 文献")
        return
    print(snippet)


def cmd_zotero_reference_pack(args):
    """Print an AI-ready reference pack."""
    pack = build_reference_pack(args.library_id, args.query, top_k=args.top_k, citation_style=args.style)
    print(pack["pack"])


def cmd_zotero_export(args):
    """Export Zotero-style references from a library."""
    print(export_references(args.library_id, fmt=args.format))


def cmd_web(args):
    """Handle 'web' command — start Flask server with port management."""
    import webbrowser
    import subprocess
    import os
    import signal
    import time

    port = args.port
    url = f"http://127.0.0.1:{port}"

    # Check if port is in use and offer to kill
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split()
            print(f"⚠️  端口 {port} 已被占用 (PID: {', '.join(pids)})")
            print("正在清理旧进程...")
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    time.sleep(0.5)
                except (ProcessLookupError, ValueError):
                    pass
            print("✅ 已清理")
    except Exception:
        pass

    # Open browser
    webbrowser.open(url)

    try:
        from ..web.app import create_app
        app = create_app()
        print(f"🌐 Web 界面启动: {url}")
        print("按 Ctrl+C 停止服务")
        app.run(debug=True, use_reloader=False, port=port, threaded=True)
    except ImportError as e:
        print(f"❌ 启动Web界面失败: {e}")
        print("请确保 Flask 已安装: pip install flask")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"❌ 端口 {port} 仍被占用，试试: pw web -p 5556")
        else:
            print(f"❌ 启动失败: {e}")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
