from pathlib import Path
from collections import Counter
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "dist", "build"}
def inspect_project(root: Path):
    exts, count, dirs, size = Counter(), 0, 0, 0
    samples = []
    for p in root.rglob("*"):
        if any(part in SKIP for part in p.parts):
            continue
        if p.is_dir():
            dirs += 1
        elif p.is_file():
            count += 1
            try: size += p.stat().st_size
            except OSError: pass
            exts[p.suffix.lower() or "[sem extensão]"] += 1
            if len(samples) < 100: samples.append(str(p.relative_to(root)))
    return {"file_count": count, "directory_count": dirs, "total_bytes": size,
            "extensions": dict(exts.most_common()), "sample_paths": samples,
            "note": "Inventário heurístico; diretórios ignorados: " + ", ".join(sorted(SKIP))}
