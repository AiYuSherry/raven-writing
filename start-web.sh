#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PORT=5555
URL="http://127.0.0.1:$PORT"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

echo "🚀 正在启动乌鸦写作台..."
env PYTHONPATH=src "$PYTHON_BIN" -m personal_writing web --port "$PORT" &
PID=$!

# 等待服务就绪
for i in {1..10}; do
    if curl -s "$URL" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# 自动打开浏览器
echo "🌐 正在打开浏览器: $URL"
if command -v open >/dev/null 2>&1; then
    open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL"
fi

# 保持脚本运行，Ctrl+C 时清理 Flask
trap 'kill $PID 2>/dev/null; exit' INT
wait $PID
