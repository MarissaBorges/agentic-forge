WEIGHTS = {"security": 30, "documentation": 20, "technical_evidence": 20, "visual": 15, "reproducibility_accessibility": 15}

def evaluate(checks):
    blockers = []
    has_critical_or_high = False
    has_warnings = False

    for c in checks:
        status = c.get("status")
        name = c.get("name")
        if name in ("secrets", "sensitive_data") and status == "FAIL":
            blockers.append(f"{name}: ocorrência(s) que exigem triagem")
        if status == "FAIL":
            has_critical_or_high = True
        elif status == "WARN":
            has_warnings = True

    # Conservador: só atribui pontos quando há PASS explícito; verificações ausentes não viram aprovação.
    mapping = {
        "secrets": ("security", 15),
        "sensitive_data": ("security", 15),
        "documentation": ("documentation", 15),
        "links": ("documentation", 5),
        "structure": ("reproducibility_accessibility", 15),
    }

    earned = {k: 0 for k in WEIGHTS}
    possible = {k: 0 for k in WEIGHTS}

    for c in checks:
        target = mapping.get(c["name"])
        if target:
            cat, max_pts = target
            possible[cat] += max_pts
            if c["status"] == "PASS":
                earned[cat] += max_pts
            elif c["status"] == "WARN" and not c.get("findings"):
                earned[cat] += max_pts * 0.8

    score = round(sum(earned.values()))

    if blockers:
        readiness = "BLOQUEADO"
    elif has_critical_or_high:
        readiness = "APTO COM RESSALVAS"
    elif has_warnings:
        readiness = "APTO COM RESSALVAS"
    elif score >= 50:
        readiness = "APTO PARA PUBLICAÇÃO"
    else:
        readiness = "APTO COM RESSALVAS"

    return {
        "score": score,
        "readiness": readiness,
        "blockers": blockers,
        "method": "Pontuação parcial conservadora: apenas checks PASS mapeados pontuam; dimensões não implementadas não são presumidas aprovadas.",
        "weights": WEIGHTS
    }
