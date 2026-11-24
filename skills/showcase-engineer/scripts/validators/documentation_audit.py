from pathlib import Path
def audit_documentation(root: Path):
    readmes = list(root.glob("README*"))
    findings = []
    if not readmes:
        findings.append({"severity":"MEDIUM","path":"README.md","message":"README não encontrado na raiz."})
    else:
        p = readmes[0]
        content = p.read_text(errors="ignore")
        if len(content.strip()) < 300:
            findings.append({"severity":"LOW","path":p.name,"message":"README muito curto; revisar contexto, instalação e uso."})
        for phrase in ("TODO", "Lorem ipsum", "replace-me", "CHANGE ME"):
            if phrase.lower() in content.lower():
                findings.append({"severity":"LOW","path":p.name,"message":f"Placeholder encontrado: {phrase}"})
    status = "FAIL" if any(x["severity"] == "MEDIUM" for x in findings) else ("WARN" if findings else "PASS")
    return {"name":"documentation","status":status,
            "summary":f"{len(findings)} achado(s) básico(s); revisão editorial e factual manual ainda necessária.",
            "findings":findings}
