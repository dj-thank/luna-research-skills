"""Trusted synthetic generators: intentionally broken variants are retained."""
import copy
import json

RECIPES = {"alpha": (41, "approved"), "beta": (42, "pending"), "gamma": (43, "unknown")}
VARIANTS = ("isolated", "roundtrip", "key-order", "shared-input", "shared-answer",
            "running-state", "wrong-answer", "wrong-input", "changed-type",
            "missing-case", "duplicate-case", "extra-case")

def builder(variant):
    def build(order):
        rows = []
        shared_input = {"revision": 0, "review": {"status": "", "owner": "root"}, "tags": ["x", "y"]}
        shared_answer = {}
        history = []
        for case_id in order:
            revision, status = RECIPES[case_id]
            source = {"revision": revision, "review": {"status": status, "owner": "root"}, "tags": ["x", "y"]}
            answer = {"ready": {"approved": True, "pending": False, "unknown": None}[status],
                      "revision": revision, "status": status}
            if variant == "shared-input":
                shared_input["revision"] = revision
                shared_input["review"]["status"] = status
                source = shared_input
            elif variant == "shared-answer":
                shared_answer.update(answer)
                answer = shared_answer
            elif variant == "running-state":
                history.append(case_id)
                source["history"] = list(history)
            elif variant == "wrong-answer":
                answer["ready"] = True
            elif variant == "wrong-input":
                source["revision"] = 0
            elif variant == "changed-type":
                answer["revision"] = float(revision)
            row = {"id": case_id, "input": source, "expected": answer}
            if variant == "roundtrip":
                row = json.loads(json.dumps(row))
            elif variant == "key-order":
                row = dict(reversed(list(row.items())))
                row["input"] = dict(reversed(list(row["input"].items())))
                row["expected"] = dict(reversed(list(row["expected"].items())))
            rows.append(row)
        if variant == "missing-case":
            rows.pop()
        elif variant == "duplicate-case":
            rows.append(copy.deepcopy(rows[0]))
        elif variant == "extra-case":
            rows.append(dict(copy.deepcopy(rows[0]), id="unplanned"))
        return rows
    return build

from pathlib import Path
from fixture_integrity import check_builder

ORACLE = Path(__file__).with_name("fixtures") / "fixture_integrity_oracle.json"
SPECS = RECIPES


def build_cases(order, shared=False):
    return builder("shared-input" if shared else "isolated")(order)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check a synthetic fixture builder against reviewed cases.")
    parser.add_argument("--variant", choices=VARIANTS, default="isolated")
    args = parser.parse_args()
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    result = check_builder(builder(args.variant), oracle["case_ids"], oracle["expected_cases"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
