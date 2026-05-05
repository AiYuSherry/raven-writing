"""CLI entry point for Personal Writing."""

import sys
import argparse
from ..core import pipeline
from ..core.style_engine import registry as style_registry
from ..db.repository import MaterialRepo, SessionRepo, ArticleRepo


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
