"""Run the local app. Ctrl+C stops only processes this launcher created."""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)


def available(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


if not available(8000) or not available(5173):
    sys.exit(
        "Ports 8000 and 5173 must be free. An existing instance may already be running; no process was stopped."
    )

processes = []


def stop(*_):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
    sys.exit(0)


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
try:
    processes.append(
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "backend",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ]
        )
    )
    npm = "npm.cmd" if os.name == "nt" else "npm"
    processes.append(
        subprocess.Popen(
            [npm, "--prefix", "frontend", "run", "dev"],
            start_new_session=os.name != "nt",
        )
    )
    print(
        "\nForma: http://127.0.0.1:5173\nAPI docs: http://127.0.0.1:8000/docs\nCtrl+C to stop.\n",
        flush=True,
    )
    while all(process.poll() is None for process in processes):
        time.sleep(1)
finally:
    # npm spawns Vite; terminate its process group too, never unrelated processes.
    for process in processes:
        if os.name != "nt" and process.args[0] == "npm":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.terminate()
