from pathlib import Path
import re
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__"}
PATTERNS = [
 ("E-mail", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
 ("Possível CPF", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
 ("Possível telefone BR", re.compile(r"(?<!\d)(?:\+55\s?)?(?:\(?\d{2}\)?\s?)9?\d{4}[- ]?\d{4}(?!\d)")),
]
def audit_sensitive_data(root: Path):
    findings, scanned = [], 0
    for p in root.rglob("*"):
        if not p.is_file() or any(x in SKIP for x in p.parts): continue
        try:
            if p.stat().st_size > 1_000_000: continue
            text = p.read_text(errors="ignore")
        except OSError: continue
        scanned += 1
        for label, rx in PATTERNS:
            for m in rx.finditer(text):
                findings.append({"severity":"HIGH", "path":str(p.relative_to(root)),
                                 "line":text.count("\n",0,m.start())+1,
                                 "message":f"Possível dado pessoal ({label}); trecho omitido"})
    return {"name":"sensitive_data", "status":"FAIL" if findings else "PASS",
            "summary":f"{len(findings)} possível(is) ocorrência(s); {scanned} arquivo(s) examinados. Falsos positivos são possíveis.",
            "findings":findings}
