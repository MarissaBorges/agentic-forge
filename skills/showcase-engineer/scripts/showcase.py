#!/usr/bin/env python3
"""Showcase Engineer CLI. Read-only by default."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from validators.project_inventory import inspect_project
from validators.secrets_audit import audit_secrets
from validators.sensitive_data_audit import audit_sensitive_data
from validators.git_history_audit import audit_git_history
from validators.documentation_audit import audit_documentation
from validators.link_checker import check_links
from validators.repository_structure import audit_structure
from analyzers.quality_score import evaluate

def main():
    parser = argparse.ArgumentParser(prog="showcase", description="Auditoria read-only de showcases GitHub")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("inspect", "audit", "audit-git", "validate-docs"):
        p = sub.add_parser(cmd)
        p.add_argument("path", type=Path)
        p.add_argument("--json", action="store_true", help="Saída JSON")
    args = parser.parse_args()
    root = args.path.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        parser.error(f"Diretório não encontrado: {root}")
    result = {"target": str(root), "generated_at": datetime.now(timezone.utc).isoformat(), "checks": []}
    if args.command == "inspect":
        result["inventory"] = inspect_project(root)
    elif args.command == "audit-git":
        result["checks"] = [audit_git_history(root)]
    elif args.command == "validate-docs":
        result["checks"] = [audit_documentation(root), check_links(root)]
    else:
        result["inventory"] = inspect_project(root)
        result["checks"] = [
            audit_secrets(root), audit_sensitive_data(root),
            audit_git_history(root), audit_documentation(root),
            check_links(root), audit_structure(root)
        ]
        result["evaluation"] = evaluate(result["checks"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Showcase Engineer — {args.command}: {root}")
        if "inventory" in result:
            inv = result["inventory"]
            print(f"Arquivos: {inv['file_count']} | Diretórios: {inv['directory_count']} | Tamanho: {inv['total_bytes']} bytes")
            print("Extensões:", ", ".join(f"{k}={v}" for k,v in inv["extensions"].items()) or "nenhuma")
        for check in result.get("checks", []):
            print(f"[{check['status']}] {check['name']}: {check['summary']}")
            for finding in check.get("findings", [])[:20]:
                print(f"  - {finding.get('severity','INFO')}: {finding.get('path','')}: {finding.get('message','')}")
        if "evaluation" in result:
            ev = result["evaluation"]
            print(f"\nStatus: {ev['readiness']} | Score: {ev['score']}/100")
            print("Bloqueios:", ", ".join(ev["blockers"]) or "nenhum identificado")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
