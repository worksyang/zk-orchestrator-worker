#!/usr/bin/env python3
"""zk-orchestrator-worker 派单执行器：默认使用 OpenCode (magpie/auto/deepseek-v4.1-flash, low 模式)，
深度支持 Antigravity (异步后台 + agy agentapi 主动唤醒双保险)，浅支持 codex / claude / pi。
仅使用 Python 3 标准库。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

sys.dont_write_bytecode = True

SKILL_NAME = "zk-orchestrator-worker"
SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
STORAGE_SCRIPT = SKILLS_ROOT / "skill_storage.py"

DEFAULT_OPENCODE_MODEL = "magpie/auto/deepseek-v4.1-flash"
DEFAULT_OPENCODE_VARIANT = "low"

ROLE_LABELS = {
    "scout": "只读侦察者",
    "worker": "全权限执行者",
    "reviewer": "独立审查者",
}

QUOTA_MARKERS = (
    "status 429", "code 429", '"code": 429', '"code":429', "http 429",
    "429 too many", "resource_exhausted", "rate limit", "rate_limit",
    "quota exceeded", "quota_exceeded", "insufficient_quota", "overloaded_error",
)
AUTH_MARKERS = (
    "not authenticated", "unauthenticated", "authentication failed",
    "401 unauthorized", "http 401", "status 401", "invalid api key",
    "token expired", "please login", "please sign in",
)


def get_storage_dir(kind: str, new: bool = False) -> Path:
    if STORAGE_SCRIPT.is_file():
        cmd = [sys.executable, "-B", str(STORAGE_SCRIPT), kind, SKILL_NAME]
        if new and kind == "tmp":
            cmd.append("--new")
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip())
    base = Path.home() / (".cache/zk-skills/tmp" if kind == "tmp" else ".local/share/zk-skills") / SKILL_NAME
    if kind != "tmp":
        base = base / kind
    base.mkdir(parents=True, exist_ok=True)
    return base


def normalize_opencode_model(model: str) -> str:
    m = (model or DEFAULT_OPENCODE_MODEL).strip()
    if m == "auto/deepseek-v4.1-flash":
        return "magpie/auto/deepseek-v4.1-flash"
    if "/" not in m:
        return f"magpie/{m}"
    return m


def find_bin(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        Path.home() / ".opencode-local" / name,
        Path.home() / ".local" / "bin" / name,
        Path("/opt/homebrew/bin") / name,
        Path("/usr/local/bin") / name,
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def build_role_prompt(role: str, raw_prompt: str) -> str:
    label = ROLE_LABELS.get(role, role)
    if role == "scout":
        prefix = (
            f"【角色：{label}（只读侦察）】\n"
            "硬性边界：只读侦察！严禁修改、新建或删除任何文件。只返回文件路径、关键行号与结构结论。\n\n"
        )
    elif role == "reviewer":
        prefix = (
            f"【角色：{label}（独立验收）】\n"
            "硬性边界：独立只读审查！严禁自行修改或修复文件。必须对照原始目标逐条给出「通过/不通过」及证据（文件路径+行号或命令输出）。\n\n"
        )
    else:
        prefix = (
            f"【角色：{label}（施工执行）】\n"
            "硬性要求：严格在指定边界内施工并运行真实验证，完成后汇报修改的文件、改动摘要与验证证据。\n\n"
        )
    return prefix + raw_prompt.strip()


def parse_opencode_json(stdout: str, stderr: str) -> Dict[str, Any]:
    texts: List[str] = []
    session_id: Optional[str] = None
    tokens: Dict[str, Any] = {}
    errors: List[str] = []

    for line in stdout.splitlines():
        line_s = line.strip()
        if not line_s.startswith("{"):
            continue
        try:
            evt = json.loads(line_s)
        except Exception:
            continue
        if not session_id and isinstance(evt.get("sessionID"), str):
            session_id = evt["sessionID"]
        etype = evt.get("type")
        part = evt.get("part") if isinstance(evt.get("part"), dict) else {}
        if etype == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        elif etype == "step_finish" and isinstance(part.get("tokens"), dict):
            tokens = part["tokens"]
        elif etype == "error":
            errors.append(json.dumps(evt, ensure_ascii=False))

    reply = "".join(texts).strip()
    if not reply and stdout.strip():
        non_json = [ln for ln in stdout.splitlines() if not ln.strip().startswith("{")]
        reply = "\n".join(non_json).strip()
    return {
        "reply": reply,
        "session_id": session_id,
        "tokens": tokens,
        "errors": errors,
        "stderr": stderr.strip(),
    }


def classify_error(text: str) -> Optional[str]:
    low = text.lower()
    if any(m in low for m in QUOTA_MARKERS):
        return "QUOTA_429"
    if any(m in low for m in AUTH_MARKERS):
        return "AUTH_401"
    return None


def build_command(
    engine: str,
    role: str,
    prompt: str,
    model: str,
    variant: str,
    session_id: Optional[str],
) -> List[str]:
    exe = find_bin(engine)
    if not exe:
        raise FileNotFoundError(f"未找到可执行文件：{engine}")

    if engine == "opencode":
        oc_model = normalize_opencode_model(model)
        oc_agent = "plan" if role in ("scout", "reviewer") else "build"
        cmd = [
            exe, "run",
            "-m", oc_model,
            "--variant", variant or DEFAULT_OPENCODE_VARIANT,
            "--agent", oc_agent,
            "--format", "json",
        ]
        if role == "worker":
            cmd.append("--auto")
        if session_id:
            cmd.extend(["-s", session_id])
        cmd.append(prompt)
        return cmd

    if engine == "codex":
        sandbox = "read-only" if role in ("scout", "reviewer") else "workspace-write"
        cmd = [exe, "exec", "--sandbox", sandbox, "--skip-git-repo-check"]
        if model and model != DEFAULT_OPENCODE_MODEL:
            cmd.extend(["-m", model])
        cmd.append(prompt)
        return cmd

    if engine == "claude":
        perm = "plan" if role in ("scout", "reviewer") else "acceptEdits"
        cmd = [exe, "-p", "--permission-mode", perm]
        if model and model != DEFAULT_OPENCODE_MODEL:
            cmd.extend(["--model", model])
        cmd.append(prompt)
        return cmd

    if engine == "pi":
        cmd = [exe, "-p"]
        if model and model != DEFAULT_OPENCODE_MODEL:
            cmd.extend(["--model", model])
        cmd.append(prompt)
        return cmd

    if engine == "agy":
        cmd = [exe, "-p", prompt, "--output-format", "json"]
        if role == "worker":
            cmd.append("--dangerously-skip-permissions")
        return cmd

    raise ValueError(f"不支持的引擎：{engine}")


def notify_antigravity(
    conversation_id: str,
    ls_address: str,
    title: str,
    content: str,
    timeout_s: int = 15,
) -> bool:
    agy_exe = os.environ.get("ANTIGRAVITY_AGENTAPI_EXE") or find_bin("agy")
    if not agy_exe or not conversation_id or not ls_address:
        return False
    env = os.environ.copy()
    env["ANTIGRAVITY_LS_ADDRESS"] = ls_address
    env.setdefault("ANTIGRAVITY_PROJECT_ID", "default-cli-project")
    argv = [
        agy_exe,
        "agentapi",
        "send-message",
        f"--title={title}",
        conversation_id,
        content,
    ]
    try:
        res = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout_s, check=False)
        return res.returncode == 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="派单提示词正文（或用 --prompt-file）")
    parser.add_argument("--prompt-file", help="从文件读取派单提示词")
    parser.add_argument(
        "--role",
        choices=("scout", "worker", "reviewer"),
        default="worker",
        help="角色：scout(只读侦察) / worker(施工执行) / reviewer(独立审查)",
    )
    parser.add_argument(
        "--engine",
        choices=("opencode", "codex", "claude", "pi", "agy"),
        default="opencode",
        help="目标 CLI 引擎（默认 opencode）",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OPENCODE_MODEL,
        help=f"模型名（默认 {DEFAULT_OPENCODE_MODEL}）",
    )
    parser.add_argument(
        "--variant",
        default=DEFAULT_OPENCODE_VARIANT,
        help=f"推理档位（默认 {DEFAULT_OPENCODE_VARIANT}）",
    )
    parser.add_argument("--cwd", default=os.getcwd(), help="子任务工作目录")
    parser.add_argument("--session", help="续接已有 opencode session ID")
    parser.add_argument("--timeout", type=int, default=1800, help="超时秒数（默认 1800s）")
    parser.add_argument(
        "--notify-agy",
        choices=("auto", "always", "never"),
        default="never",
        help="完工后是否调用 agy agentapi send-message 主动推送（默认 never 靠原生后台任务唤醒， detached 模式用 always）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结构化结果")
    args = parser.parse_args()

    raw_prompt = args.prompt or ""
    if args.prompt_file:
        raw_prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8")
    if not raw_prompt.strip():
        parser.error("必须提供派单提示词（位置参数 prompt 或 --prompt-file）")

    full_prompt = build_role_prompt(args.role, raw_prompt)
    cwd = str(Path(args.cwd).expanduser().resolve())
    cmd = build_command(args.engine, args.role, full_prompt, args.model, args.variant, args.session)

    task_dir = get_storage_dir("tmp", new=True)
    started = time.time()
    timed_out = False

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
        stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        stderr = (exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
        exit_code = 124

    elapsed = round(time.time() - started, 2)

    if args.engine == "opencode":
        parsed = parse_opencode_json(stdout, stderr)
        reply = parsed["reply"]
        session_id = parsed["session_id"]
        tokens = parsed["tokens"]
    else:
        reply = stdout.strip() or stderr.strip()
        session_id = None
        tokens = {}

    combined_err = f"{stderr}\n{stdout}" if exit_code != 0 else stderr
    err_kind = "TIMEOUT" if timed_out else (classify_error(combined_err) if exit_code != 0 else None)
    status = "ok" if (exit_code == 0 and bool(reply)) else ("timeout" if timed_out else "error")

    result_payload = {
        "status": status,
        "engine": args.engine,
        "role": args.role,
        "role_label": ROLE_LABELS.get(args.role, args.role),
        "model": normalize_opencode_model(args.model) if args.engine == "opencode" else args.model,
        "variant": args.variant if args.engine == "opencode" else None,
        "cwd": cwd,
        "exit_code": exit_code,
        "error_kind": err_kind,
        "elapsed_sec": elapsed,
        "session_id": session_id,
        "tokens": tokens,
        "log_dir": str(task_dir),
        "reply": reply,
        "stderr": stderr.strip()[:1000] if exit_code != 0 else "",
    }

    (task_dir / "result.json").write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (task_dir / "stdout.log").write_text(stdout, encoding="utf-8")
    if stderr:
        (task_dir / "stderr.log").write_text(stderr, encoding="utf-8")

    conv_id = os.environ.get("ANTIGRAVITY_CONVERSATION_ID", "")
    ls_addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS", "")
    should_push = args.notify_agy == "always" or (args.notify_agy == "auto" and status != "ok")
    if should_push and conv_id and ls_addr:
        summary_msg = (
            f"[子代理完工汇报 | {args.engine} · {ROLE_LABELS.get(args.role, args.role)} | {elapsed}s]\n"
            f"状态: {status} (session: {session_id or 'N/A'})\n\n"
            f"{reply[:3500]}"
        )
        notify_antigravity(conv_id, ls_addr, f"subagent-{args.role}", summary_msg)

    if args.json:
        print(json.dumps(result_payload, ensure_ascii=False, indent=2))
    else:
        header = (
            f"[DISPATCH_RESULT | engine={args.engine} | role={args.role}({ROLE_LABELS.get(args.role, args.role)}) "
            f"| model={result_payload['model']} | variant={result_payload['variant']} "
            f"| status={status} | elapsed={elapsed}s | session={session_id or 'none'}]"
        )
        print(header)
        if reply:
            print(reply)
        if status != "ok" and stderr.strip():
            print(f"\n[STDERR]\n{stderr.strip()[:1500]}", file=sys.stderr)

    return 0 if status == "ok" else (exit_code or 1)


if __name__ == "__main__":
    raise SystemExit(main())
