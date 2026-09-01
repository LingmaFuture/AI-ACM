import json
import subprocess
import sys
from pathlib import Path

from .config import settings


class JudgeUnavailable(RuntimeError):
    pass


class JudgeExecutor:
    def run(self, payload: dict) -> dict:
        encoded = json.dumps(payload, ensure_ascii=False)
        limits = payload.get("resource_limits", {})
        timeout = settings.judge_total_timeout_seconds
        if settings.judge_mode == "docker":
            command = [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "64",
                "--cpus",
                "1.0",
                "--memory",
                f"{int(limits.get('memory_mb', 256))}m",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                settings.judge_image,
            ]
            cwd = None
        else:
            command = [sys.executable, "-m", "app.runner"]
            cwd = Path(__file__).resolve().parent.parent
        try:
            completed = subprocess.run(
                command,
                input=encoded,
                text=True,
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise JudgeUnavailable(f"无法启动判题环境：{exc}") from exc
        if completed.returncode != 0:
            raise JudgeUnavailable(f"判题环境异常退出：{completed.stderr[-500:]}")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise JudgeUnavailable("判题环境返回了无效结果") from exc


judge_executor = JudgeExecutor()

