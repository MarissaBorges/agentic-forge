from pathlib import Path
RECOMMENDED = ["README.md", "LICENSE", ".gitignore"]
def audit_structure(root: Path):
    findings=[]
    for name in RECOMMENDED:
        if not (root/name).exists():
            findings.append({"severity":"LOW","path":name,"message":f"{name} ausente (avaliar se é aplicável)."})
    return {"name":"structure","status":"WARN" if findings else "PASS",
            "summary":f"{len(findings)} item(ns) estrutural(is) para revisar.",
            "findings":findings}
