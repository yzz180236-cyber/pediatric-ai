import argparse
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DEFAULT_RAW_DIR = ROOT_DIR / "data" / "raw"
IMPORT_SCRIPT = SCRIPT_DIR / "knowledge_import.py"


def run_import(target_dir: Path) -> int:
    if not target_dir.exists():
        print(f"❌ 目录不存在: {target_dir}")
        return 1

    cmd = [sys.executable, str(IMPORT_SCRIPT), "--dir", str(target_dir)]
    print(f"🚀 启动知识库导入: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT_DIR))


def list_sources(target_dir: Path) -> int:
    if not target_dir.exists():
        print(f"❌ 目录不存在: {target_dir}")
        return 1

    files = sorted(
        [
            path
            for path in target_dir.rglob("*")
            if path.suffix.lower() in {".pdf", ".txt"}
        ]
    )
    if not files:
        print("暂无可导入文档，请先放入 .pdf 或 .txt 文件。")
        return 0

    print("可导入知识源：")
    for file in files:
        print(f"- {file.relative_to(target_dir)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="智慧儿科知识库管理 CLI")
    parser.add_argument("command", choices=["import", "list"], help="执行的命令")
    parser.add_argument(
      "--dir",
      default=str(DEFAULT_RAW_DIR),
      help="知识源目录，默认 services/ai-engine/data/raw",
    )
    args = parser.parse_args()

    target_dir = Path(args.dir).resolve()
    if args.command == "list":
      return list_sources(target_dir)
    if args.command == "import":
      return run_import(target_dir)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
