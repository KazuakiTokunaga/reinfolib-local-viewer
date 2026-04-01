from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"
ENV_LOCAL_PATH = FRONTEND_DIR / ".env.local"
ENV_LOCAL_EXAMPLE_PATH = FRONTEND_DIR / ".env.local.example"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FastAPI バックエンドと Next.js フロントエンドを同時に起動します。"
    )
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--frontend-mode", choices=("dev", "start"), default="dev")
    return parser.parse_args()


def ensure_frontend_env() -> None:
    if not ENV_LOCAL_PATH.exists() and ENV_LOCAL_EXAMPLE_PATH.exists():
        shutil.copyfile(ENV_LOCAL_EXAMPLE_PATH, ENV_LOCAL_PATH)


def stream_output(process: subprocess.Popen[str], prefix: str) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{prefix}] {line}", end="")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start_process(
    command: list[str],
    cwd: Path,
    prefix: str,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    threading.Thread(
        target=stream_output,
        args=(process, prefix),
        daemon=True,
    ).start()
    return process


def main() -> None:
    args = parse_args()
    ensure_frontend_env()

    frontend_env = os.environ.copy()
    frontend_env["NEXT_PUBLIC_API_BASE_URL"] = (
        f"http://127.0.0.1:{args.backend_port}"
    )

    backend_process = start_process(
        [
            "uv",
            "run",
            "uvicorn",
            "backend.app.main:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.backend_port),
        ],
        cwd=REPO_ROOT,
        prefix="backend",
    )
    frontend_process = start_process(
        [
            "npm",
            "run",
            args.frontend_mode,
            "--",
            "--hostname",
            "127.0.0.1",
            "--port",
            str(args.frontend_port),
        ],
        cwd=FRONTEND_DIR,
        prefix="frontend",
        env=frontend_env,
    )

    def handle_signal(signum: int, _frame: object) -> None:
        print(f"\n[launcher] signal={signum} received, stopping processes...")
        terminate_process(frontend_process)
        terminate_process(backend_process)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(
        "[launcher]"
        f" backend=http://127.0.0.1:{args.backend_port}"
        f" frontend=http://127.0.0.1:{args.frontend_port}"
        f" mode={args.frontend_mode}"
    )
    print("[launcher] press Ctrl+C to stop both processes")

    try:
        while True:
            backend_code = backend_process.poll()
            frontend_code = frontend_process.poll()
            if backend_code is not None or frontend_code is not None:
                print(
                    "[launcher] process exited:"
                    f" backend={backend_code} frontend={frontend_code}"
                )
                break
            time.sleep(0.5)
    finally:
        terminate_process(frontend_process)
        terminate_process(backend_process)

    if backend_process.returncode not in (None, 0):
        raise SystemExit(backend_process.returncode)
    if frontend_process.returncode not in (None, 0):
        raise SystemExit(frontend_process.returncode)


if __name__ == "__main__":
    main()
