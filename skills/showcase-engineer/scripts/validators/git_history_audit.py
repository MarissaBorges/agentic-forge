from pathlib import Path
import subprocess
def run(root, args):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, timeout=60)
def audit_git_history(root: Path):
    if not (root / ".git").exists():
        return {"name":"git_history","status":"NOT RUN","summary":"Diretório não é um repositório Git; histórico não verificado.","findings":[]}
    try:
        refs = run(root, ["for-each-ref", "--format=%(refname)"])
        log = run(root, ["log", "--all", "--full-history", "--format=%H", "--name-only"])
        if refs.returncode or log.returncode:
            raise RuntimeError(refs.stderr or log.stderr)
        commits = len([x for x in log.stdout.splitlines() if len(x)==40 or len(x)==64])
        paths = sorted({x for x in log.stdout.splitlines() if x and not (len(x)==40 or len(x)==64)})
        return {"name":"git_history","status":"WARN",
                "summary":f"{commits} commit(s) e {len(paths)} caminho(s) vistos nas refs acessíveis. Conteúdo histórico ainda requer scanner de segredos.",
                "findings":[],"refs":refs.stdout.splitlines(),"historical_paths_sample":paths[:100],
                "note":"Não inspeciona automaticamente blobs antigos; combine com Gitleaks/detect-secrets em todas as refs."}
    except Exception as e:
        return {"name":"git_history","status":"NOT RUN","summary":f"Falha ao consultar Git: {type(e).__name__}","findings":[]}
