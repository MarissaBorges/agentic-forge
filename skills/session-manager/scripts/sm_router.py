#!/usr/bin/env python3
"""Deterministic intent/command router with typo tolerance and risk classification."""
from __future__ import annotations

import re
from typing import Any

_ALIASES = {
    "optmize": "optimize",
    "optimise": "optimize",
    "recovr": "recover",
    "recovey": "recover",
    "statu": "status",
    "staus": "status",
    "handof": "handoff",
    "audti": "audit",
    "decison": "decision",
    "decisions": "decision",
    "tasks": "task",
}

_DESTRUCTIVE_RE = re.compile(
    r"(?i)\b(?:force[- ]push|push\s+--force|rm\s+-rf|reset\s+--hard|drop\s+table|"
    r"truncate\s+table|delete\s+all|destroy|deploy|publish|release\s+to\s+prod|"
    r"apagar\s+tudo|excluir\s+tudo|publicar)\b"
)


def route_request(raw_input: str) -> dict[str, Any]:
    """Parse slash commands or natural-language prompts into module, action, args, and risk."""
    text = raw_input.strip()
    cleaned = re.sub(r"^/session-manager\b\s*", "", text, flags=re.I).strip()

    risk = "destructive" if _DESTRUCTIVE_RE.search(cleaned) else "reversible"
    if risk == "destructive":
        return {
            "raw": raw_input,
            "module": "safety-gate",
            "action": "require_approval",
            "args": cleaned,
            "risk": risk,
            "interaction_mode": "require_approval",
            "reason": "Request matches destructive or externally consequential action boundary.",
        }

    if not cleaned:
        return {
            "raw": raw_input,
            "module": "help",
            "action": "show",
            "args": "",
            "risk": "reversible",
            "interaction_mode": "clarify",
            "reason": "No command or intent provided.",
        }

    tokens = cleaned.split()
    head = _ALIASES.get(tokens[0].lower(), tokens[0].lower())
    rest = " ".join(tokens[1:]).strip()

    if head in ("help", "init", "recover", "status", "handoff", "audit"):
        return {
            "raw": raw_input,
            "module": head,
            "action": "run",
            "args": rest,
            "risk": "reversible",
            "interaction_mode": "execute",
            "reason": "Direct reversible module command.",
        }

    if head == "optimize":
        mode = "plan" if len(rest.split()) <= 4 else "execute"
        return {
            "raw": raw_input,
            "module": "optimize",
            "action": "diagnose",
            "args": rest,
            "risk": "reversible",
            "interaction_mode": mode,
            "reason": "Diagnostic-first performance workflow; measure before editing.",
        }

    if head == "task":
        sub_tokens = rest.split()
        sub = sub_tokens[0].lower() if sub_tokens else "list"
        sub_args = " ".join(sub_tokens[1:]).strip() if len(sub_tokens) > 1 else ""
        if sub not in ("start", "list", "show", "update", "complete", "cancel"):
            return {
                "raw": raw_input,
                "module": "task",
                "action": "start",
                "args": rest,
                "risk": "reversible",
                "interaction_mode": "execute",
                "reason": "Inferred task creation from free-form task text.",
            }
        return {
            "raw": raw_input,
            "module": "task",
            "action": sub,
            "args": sub_args,
            "risk": "reversible",
            "interaction_mode": "execute",
            "reason": "Explicit task subcommand.",
        }

    if head == "decision":
        sub_tokens = rest.split()
        sub = sub_tokens[0].lower() if sub_tokens else "list"
        sub_args = " ".join(sub_tokens[1:]).strip() if len(sub_tokens) > 1 else ""
        if sub not in ("record", "list", "show", "status"):
            sub, sub_args = "record", rest
        return {
            "raw": raw_input,
            "module": "decision",
            "action": sub,
            "args": sub_args,
            "risk": "reversible",
            "interaction_mode": "execute",
            "reason": "Explicit decision tracking command.",
        }

    # Natural-language PT-BR / EN fallbacks
    lower = cleaned.lower()
    if any(k in lower for k in ("lento", "lentidão", "lentidao", "slow", "gargalo", "bottleneck", "performance")):
        return {
            "raw": raw_input,
            "module": "optimize",
            "action": "diagnose",
            "args": cleaned,
            "risk": "reversible",
            "interaction_mode": "execute",
            "reason": "Matched natural-language performance symptom.",
        }
    if any(k in lower for k in ("retomar", "recuperar", "continuar", "onde parei", "resume", "recover context")):
        return {
            "raw": raw_input,
            "module": "recover",
            "action": "run",
            "args": cleaned,
            "risk": "reversible",
            "interaction_mode": "execute",
            "reason": "Matched natural-language context recovery intent.",
        }
    if any(k in lower for k in ("handoff", "encerrar sessão", "encerrar sessao", "fechar sessão", "passar bastão")):
        return {
            "raw": raw_input,
            "module": "handoff",
            "action": "run",
            "args": cleaned,
            "risk": "reversible",
            "interaction_mode": "execute",
            "reason": "Matched natural-language session handoff intent.",
        }
    if any(k in lower for k in ("auditar", "auditoria", "integridade", "check integrity")):
        return {
            "raw": raw_input,
            "module": "audit",
            "action": "run",
            "args": cleaned,
            "risk": "reversible",
            "interaction_mode": "execute",
            "reason": "Matched natural-language context audit intent.",
        }
    if any(k in lower for k in ("decisão", "decisao", "adr", "arquitetural")):
        return {
            "raw": raw_input,
            "module": "decision",
            "action": "record",
            "args": cleaned,
            "risk": "reversible",
            "interaction_mode": "execute",
            "reason": "Matched natural-language decision tracking intent.",
        }

    return {
        "raw": raw_input,
        "module": "task",
        "action": "start",
        "args": cleaned,
        "risk": "reversible",
        "interaction_mode": "plan" if len(tokens) > 8 else "clarify",
        "reason": "Ambiguous free-form request; plan or ask one focused question before broad edits.",
    }
