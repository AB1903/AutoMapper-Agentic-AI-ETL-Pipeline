#!/usr/bin/env python3
"""
run.py
=======
Local development server launcher for AutoMapper.

Usage:
    python run.py               # start on port 8003
    python run.py --port 8080   # custom port
    python run.py --reload      # auto-reload on code changes
"""

import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Start AutoMapper API server")
    parser.add_argument("--host",   default="0.0.0.0",  help="Bind host")
    parser.add_argument("--port",   default=8003, type=int, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on changes")
    parser.add_argument("--workers", default=1, type=int, help="Number of workers")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.api.main:app",
        "--host",    args.host,
        "--port",    str(args.port),
        "--workers", str(args.workers),
        "--log-level", "info",
    ]
    if args.reload:
        cmd.append("--reload")

    print(f"""
╔══════════════════════════════════════════════════════╗
║           AutoMapper — Starting API Server           ║
╠══════════════════════════════════════════════════════╣
║  URL:     http://localhost:{args.port}                   ║
║  Docs:    http://localhost:{args.port}/docs               ║
║  Health:  http://localhost:{args.port}/health             ║
╚══════════════════════════════════════════════════════╝

Pre-flight checklist:
  1. Ollama running?   → ollama serve
  2. Model pulled?     → ollama pull codellama:7b
  3. PostgreSQL up?    → docker-compose up postgres -d
""")

    subprocess.run(cmd)


if __name__ == "__main__":
    main()
