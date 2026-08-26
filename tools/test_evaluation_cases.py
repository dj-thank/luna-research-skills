from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tools" / "evaluation_cases.json"
ALLOWED_SKILLS = {
    "none",
    "root_only",
    "run-diverse-luna-research",
    "run-diverse-luna-project",
}
ALLOWED_MODES = {"single_root", "root_only", "flat", "hierarchical"}


class RouteEvaluationManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(CASES.read_text(encoding="utf-8"))

    def test_manifest_has_unique_well_formed_cases(self) -> None:
        self.assertIsInstance(self.cases, list)
        self.assertGreaterEqual(len(self.cases), 12)
        identifiers = [case.get("id") for case in self.cases]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for case in self.cases:
            self.assertIsInstance(case.get("id"), str)
            self.assertTrue(case["id"])
            self.assertIsInstance(case.get("prompt"), str)
            self.assertGreaterEqual(len(case["prompt"]), 20)
            self.assertIn(case.get("expected_skill"), ALLOWED_SKILLS)
            self.assertIn(case.get("expected_mode"), ALLOWED_MODES)
            self.assertIsInstance(case.get("required_controls"), list)
            self.assertTrue(case["required_controls"])
            self.assertEqual(len(case["required_controls"]), len(set(case["required_controls"])))

    def test_manifest_covers_positive_negative_and_root_only_routes(self) -> None:
        routes = {case["expected_skill"] for case in self.cases}
        self.assertEqual(routes, ALLOWED_SKILLS)
        modes = {case["expected_mode"] for case in self.cases}
        self.assertEqual(modes, ALLOWED_MODES)

    def test_delivery_prompts_route_to_project(self) -> None:
        delivery_ids = {
            "audit-fix-release",
            "api-research-and-components",
            "provider-deployment",
            "nationwide-catalog",
            "multi-artifact-release",
        }
        by_id = {case["id"]: case for case in self.cases}
        for identifier in delivery_ids:
            self.assertEqual(by_id[identifier]["expected_skill"], "run-diverse-luna-project")

    def test_implicit_discovery_and_explicit_delivery_boundary(self) -> None:
        project_yaml = (ROOT / ".agents/skills/run-diverse-luna-project/agents/openai.yaml").read_text(encoding="utf-8")
        research_yaml = (ROOT / ".agents/skills/run-diverse-luna-research/agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: true", project_yaml)
        self.assertIn("allow_implicit_invocation: true", research_yaml)
        self.assertIn("explicitly requested", project_yaml)
        self.assertIn("evidence packet", research_yaml)
        self.assertIn("only when I explicitly requested Luna implementation", research_yaml)

    def test_safety_and_verification_controls_are_represented(self) -> None:
        controls = {
            control
            for case in self.cases
            for control in case["required_controls"]
        }
        for required in (
            "runtime_receipt",
            "adversarial_quota",
            "no_secret_delegation",
            "external_write_gate",
            "independent_verifier",
            "root_integration",
            "no_unnecessary_fanout",
        ):
            self.assertIn(required, controls)


if __name__ == "__main__":
    unittest.main()
