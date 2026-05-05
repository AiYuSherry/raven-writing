"""Claude Code CLI subprocess wrapper."""

import subprocess
import json
import tempfile
import os
import shutil
import signal
import threading


CLAUDE_CMD = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
_ACTIVE_PROCESSES = set()
_ACTIVE_LOCK = threading.Lock()


def is_available():
    """Check if Claude Code CLI is available."""
    return CLAUDE_CMD is not None and os.path.isfile(CLAUDE_CMD)


def call(prompt, max_retries=1):
    """Call Claude Code CLI with a prompt and return the response text.

    Uses a temp file to pass the prompt and capture output.
    Falls back to direct subprocess if tempfile approach fails.
    """
    if not is_available():
        raise RuntimeError(
            "Claude Code CLI not found. Install it first: https://claude.ai/code"
        )

    for attempt in range(max_retries + 1):
        try:
            return _call_internal(prompt)
        except Exception as e:
            if "生成已停止" in str(e):
                raise
            if attempt == max_retries:
                raise
            continue


def _call_internal(prompt):
    """Execute Claude Code with a prompt and capture output."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(prompt)
        prompt_path = f.name

    try:
        proc = subprocess.Popen(
            [CLAUDE_CMD, "--print", prompt_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "CLAUDE_CODE_QUIET_MODE": "true"},
            start_new_session=True,
        )
        with _ACTIVE_LOCK:
            _ACTIVE_PROCESSES.add(proc)
        try:
            stdout, stderr = proc.communicate(timeout=300)
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_PROCESSES.discard(proc)
        if proc.returncode is not None and proc.returncode < 0:
            raise RuntimeError("生成已停止")
        output = (stdout or "") + "\n" + (stderr or "")
        return output.strip()
    except subprocess.TimeoutExpired:
        _terminate_process(proc)
        raise RuntimeError("Claude Code CLI timed out after 300 seconds")
    finally:
        os.unlink(prompt_path)


def _terminate_process(proc):
    """Terminate a Claude Code subprocess and its child process group."""
    if proc.poll() is not None:
        return False
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return False


def cancel_active_calls():
    """Cancel currently running Claude Code calls."""
    with _ACTIVE_LOCK:
        processes = list(_ACTIVE_PROCESSES)
    cancelled = 0
    for proc in processes:
        if _terminate_process(proc):
            cancelled += 1
            with _ACTIVE_LOCK:
                _ACTIVE_PROCESSES.discard(proc)
    return cancelled


def call_with_style(prompt_template, style_config, material_content):
    """Call Claude Code with a style-specific prompt template.

    Args:
        prompt_template: The style's prompt template string
        style_config: Dict of style parameters
        material_content: The raw material to write from

    Returns:
        Response text from Claude Code
    """
    full_prompt = f"""{prompt_template}

## 素材内容
{material_content}

## 写作要求
- 目标字数：约{style_config.get('word_count', 1000)}字
- 语气：{style_config.get('tone', 'natural')}
- 结构：{style_config.get('structure', 'free')}
- 人称视角：{style_config.get('personal_pronoun', 'first_person')}

【重要】只输出文章内容本身，不要创建任何文件，不要保存到磁盘，不要输出额外解释。"""
    return call(full_prompt)
