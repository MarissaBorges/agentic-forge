import unittest
import sys
from pathlib import Path

# Garantir que a raiz dos scripts esteja no path
BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from analyzers.quality_score import evaluate

class TestQualityScore(unittest.TestCase):
    def test_secret_failure_blocks(self):
        result = evaluate([{"name": "secrets", "status": "FAIL"}])
        self.assertEqual(result["readiness"], "BLOQUEADO")
        self.assertEqual(result["score"], 0)
        self.assertIn("secrets: ocorrência(s) que exigem triagem", result["blockers"])

    def test_missing_checks_do_not_pass(self):
        result = evaluate([])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["readiness"], "APTO COM RESSALVAS")

    def test_all_pass_ready_for_publication(self):
        checks = [
            {"name": "secrets", "status": "PASS"},
            {"name": "sensitive_data", "status": "PASS"},
            {"name": "documentation", "status": "PASS"},
            {"name": "links", "status": "PASS"},
            {"name": "structure", "status": "PASS"}
        ]
        result = evaluate(checks)
        self.assertEqual(result["readiness"], "APTO PARA PUBLICAÇÃO")
        self.assertEqual(result["score"], 65)
        self.assertEqual(result["blockers"], [])

    def test_warnings_result_in_apt_with_reservations(self):
        checks = [
            {"name": "secrets", "status": "PASS"},
            {"name": "sensitive_data", "status": "PASS"},
            {"name": "documentation", "status": "PASS"},
            {"name": "links", "status": "PASS"},
            {"name": "structure", "status": "WARN", "findings": [{"message": "LICENSE ausente"}]}
        ]
        result = evaluate(checks)
        self.assertEqual(result["readiness"], "APTO COM RESSALVAS")
        self.assertEqual(result["score"], 50)

if __name__ == "__main__":
    unittest.main()
