from pathlib import Path
import re
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__"}
PATTERNS = [
 ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
 ("Private key header", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
 ("Generic credential assignment", re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
 ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
 ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{15,}\b")),
]
def audit_secrets(root: Path):
    findings, scanned = [], 0
    for p in root.rglob("*"):
        if not p.is_file() or any(x in SKIP for x in p.parts): continue
        try:
            if p.stat().st_size > 2_000_000: continue
            data = p.read_text(errors="ignore")
        except (OSError, UnicodeError): continue
        scanned += 1
        for label, rx in PATTERNS:
            for m in rx.finditer(data):
                line = data.count("\n", 0, m.start()) + 1
                findings.append({"severity":"CRITICAL", "path":str(p.relative_to(root)),
                                 "line":line, "message":f"Padrão compatível com {label}; valor omitido"})
    return {"name":"secrets", "status":"FAIL" if findings else "PASS",
            "summary":f"{len(findings)} ocorrência(s) heurística(s); {scanned} arquivo(s) examinados. Use scanner dedicado.",
            "findings":findings, "tool":"built-in-pattern-scanner"}
