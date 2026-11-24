from pathlib import Path
import re
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
def check_links(root: Path):
    findings=[]
    for p in root.rglob("*.md"):
        if ".git" in p.parts: continue
        try: txt=p.read_text(errors="ignore")
        except OSError: continue
        for target in LINK.findall(txt):
            target=target.strip().split()[0].strip("<>")
            if target.startswith(("http://","https://","mailto:","#")): continue
            dest=(p.parent/target.split("#")[0]).resolve()
            if target.split("#")[0] and not dest.exists():
                findings.append({"severity":"MEDIUM","path":str(p.relative_to(root)),
                                 "message":f"Link local quebrado: {target}"})
    return {"name":"links","status":"FAIL" if findings else "PASS",
            "summary":f"{len(findings)} link(s) local(is) quebrado(s); links externos não foram acessados.",
            "findings":findings}
