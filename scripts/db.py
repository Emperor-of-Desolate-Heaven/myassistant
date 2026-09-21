#!/usr/bin/env python3
"""个人数据库工具:index / search / show / stats。纯标准库,无第三方依赖。

用法:
  py scripts/db.py index                # 重建索引
  py scripts/db.py search <词>...       # 全文检索(全部词都命中)
  py scripts/db.py search -C 3 <词>     # 扩大上下文行数
  py scripts/db.py show data/xx.md      # 带行号查看条目
  py scripts/db.py stats                # 各目录统计
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE = DATA / "state"

# 参与索引/检索的资料目录(state 等机器状态除外)
SOURCES = [DATA / "profile", DATA / "contacts", DATA / "events", DATA / "archive"]


def md_files():
    for src in SOURCES:
        if src.is_dir():
            yield from sorted(src.rglob("*.md"))


def cmd_index(_args):
    records = []
    for f in md_files():
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            print(f"[skip] {f}: {e}", file=sys.stderr)
            continue
        title = next((l[2:].strip() for l in lines if l.startswith("# ")), f.stem)
        headings = [l.strip() for l in lines if re.match(r"^#{1,6} ", l)]
        records.append({
            "path": str(f.relative_to(ROOT)).replace("\\", "/"),
            "title": title,
            "headings": headings,
            "lines": len(lines),
            "mtime": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    STATE.mkdir(parents=True, exist_ok=True)
    out = STATE / "index.json"
    out.write_text(json.dumps(
        {"generated": datetime.now(timezone.utc).isoformat(), "records": records},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"索引已重建:{len(records)} 个文件 -> {out.relative_to(ROOT)}")


def cmd_search(args):
    pats = [re.compile(t, re.IGNORECASE) for t in args.terms]
    total = 0
    for f in md_files():
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        hits = [i for i, line in enumerate(lines, 1) if any(p.search(line) for p in pats)]
        if not hits:
            continue
        total += len(hits)
        print(f"## {rel} ({len(hits)} 处)")
        for i in hits:
            lo, hi = max(1, i - args.context), min(len(lines), i + args.context)
            for j in range(lo, hi + 1):
                mark = ">" if j == i else " "
                print(f"{mark} {rel}:{j}: {lines[j-1]}")
            print()
    print(f"共 {total} 处匹配" if total else "无匹配")


def cmd_show(args):
    for name in args.paths:
        f = (ROOT / name).resolve()
        if not f.is_file():
            print(f"[skip] 不存在:{name}", file=sys.stderr)
            continue
        print(f"## {name}")
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            print(f"{i:4} | {line}")
        print()


def cmd_stats(_args):
    for src in SOURCES:
        if not src.is_dir():
            continue
        files = list(src.rglob("*.md"))
        lines = sum(len(f.read_text(encoding="utf-8").splitlines()) for f in files)
        print(f"{str(src.relative_to(ROOT)):>16}  {len(files):3} 个文件 {lines:5} 行")


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="个人数据库")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index", help="重建索引")
    s = sub.add_parser("search", help="全文检索(多个词都须命中)")
    s.add_argument("terms", nargs="+")
    s.add_argument("-C", "--context", type=int, default=1)
    sh = sub.add_parser("show", help="带行号查看条目")
    sh.add_argument("paths", nargs="+")
    sub.add_parser("stats", help="统计")
    args = p.parse_args()
    {"index": cmd_index, "search": cmd_search, "show": cmd_show, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    main()
