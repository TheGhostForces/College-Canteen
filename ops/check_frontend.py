"""Проверка синтаксиса отдельных JS-файлов и inline ES-модулей без исполнения."""

import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "frontend"
for path in sorted(root.rglob("*.js")):
    subprocess.run(["node", "--check", str(path)], check=True)
for path in sorted(root.rglob("*.html")):
    for index, match in enumerate(re.finditer(r"<script\b([^>]*)>(.*?)</script\s*>", path.read_text(), re.S | re.I)):
        attributes, source = match.groups()
        if re.search(r"\bsrc\s*=", attributes) or not source.strip():
            continue
        result = subprocess.run(
            ["node", "--check", "--input-type=module"],
            input=source,
            text=True,
            capture_output=True,
        )
        if result.returncode:
            raise SystemExit(f"{path.relative_to(root)} script #{index + 1}:\n{result.stderr}")
print("Frontend JavaScript syntax OK")
