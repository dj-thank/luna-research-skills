# Project ledger contract

## Hierarchy fields (v2)

Set `mode` to `flat` or `hierarchical`; use hierarchical when six or more independent cells are ready. A tree is `root depth=0 -> coordinator depth=1 -> leaf depth=2`; `max_workflow_depth=2`, and leaves have `may_spawn_descendants=false`. `N` is one global attempt budget shared by coordinator, leaf, probe, retry, and verifier. `C` is capacity and `W` is the total number of starts in one numbered wave; require `W <= min(C,N)` and never substitute one control for another. Reserve `verifier_reserve_V=max(1,ceil(.15*N))`. Add to every assignment: `tree_id`, `attempt_budget_N`, `concurrency_cap_C`, `wave_width_W`, `max_workflow_depth`, `parent_attempt_id`, `delegated_by`, `depth`, `wave`, `planned_at`, `started_at`, `finished_at`, `retry_of`, `descendant_budget`, `planned_child_attempt_ids`, `collected_result_ids`, `may_spawn_descendants`, `ttl_seconds`, `epoch`, `retry_owner`, `dedup_key`, and `cancel_reason`. Require exact parent-edge runtime provenance; static role names and TOMLs never suffice. A writable effective sandbox must not be labeled read-only.

Keep one UTF-8 JSON ledger for every project run. It is the machine-readable boundary between planned child work, verified child receipts, root integration, evidence gates, and closure. The ledger tracks spawned child attempts only; root-owned integration and external operations are represented by top-level status and gate receipts, not by pretending the root is a child assignment.

## Required top-level fields

- `ledger_type`: exactly `project`.
- `version`: `2`.
- `phase`: `planning`, `integration`, or `closure`.
- `closure_status`: `open`, then `complete` or `blocked` only in closure.
- `N`: fixed positive assignment-attempt budget chosen by root; practical project bands are 4-8, 8-16, and 16-32. Do not treat any numeric band as a platform guarantee; validate against live/config capacity.
- `verifier_reserve_V`: exactly `max(1,ceil(.15*N))`; optional work cannot spend it.
- `overall_deadline`: timezone-aware ISO-8601 timestamp.
- `root_integration_status`: `not_started`, `in_progress`, `completed`, or `blocked`.
- `root_integration_receipt`: null until a precise diff, artifact, command, or report locator exists.
- `target_gate`: one of `LOCAL_PASS`, `DEVICE_PASS`, `PROVIDER_PASS`, `PUBLIC_PASS`, or `HUMAN_GO`.
- `verified_gates`: a contiguous prefix beginning with `LOCAL_PASS`; never skip a gate.
- `gate_receipts`: one non-empty locator for every verified gate.
- `external_authority`: boolean; required true before `PROVIDER_PASS`, `PUBLIC_PASS`, or `HUMAN_GO` can be recorded.
- `assignments`: no more than `N` child-attempt rows.

## Assignment row

Every row requires:

- `attempt_id`, `kind`, and one bounded `objective`;
- `kind`: `builder`, `evidence_lane`, `reviewer`, `verifier`, or `operator`;
- non-empty `ownership`; concurrent accepted builders/operators may not share an ownership path;
- `dependencies`, referencing only earlier attempt IDs;
- assignment `deadline`, `acceptance_criteria`, and an exact `evidence_locator`;
- `execution_status` and `acceptance_status` using the research state machine: `planned/pending`, terminal root-only `not_dispatched/excluded`, or actual child work ending in `completed`, `failed`, `timed_out`, or `abandoned`;
- `integration_status`: `not_applicable`, `pending`, `integrated`, or `rejected`.

For an evidence lane, also include `source_plane`, `access_mode`, and `safety_enforcement`. `prompt_only_public` is valid only for `public_web`. `connector_private` and `provider` remain `root_only` while external tool permissions cannot be mechanically proven. A root-only row closes without child runtime metadata as `not_dispatched/excluded`, with a terminal timestamp and explicit gap. Work may not start after its assignment or overall deadline, and a late completion may not be accepted.

Every accepted child row also requires `thread_uuid`, exact `runtime_turn`, `agent_role`, `runtime_model=gpt-5.6-luna`, `runtime_effort=medium`, `safety_enforcement`, `runtime_verified=true`, `parent_thread_uuid`, `parent_call_id`, and `spawn_kind=spawn_agent`. Follow-up turns are not accepted production receipts.

Evidence-lane rows use source plane enum `public_web|local|internal_session|connector_private|provider`, plus freshness status, exact locator or content hash, unknowns, and gap reason. Keep source-plane comparisons explicit; never infer a higher evidence gate from a lower-plane observation.

### Canonical JSON field table

| Field | Meaning | Canonical rule |
|---|---|---|
| `tree_id`, `run_id` | UUID identities | both required; no human-label substitutes |
| `attempt_budget_N`, `concurrency_cap_C`, `wave_width_W`, `max_workflow_depth`, `verifier_reserve_V` | global controls | require `W<=C`, `W<=N`, and `V=max(1,ceil(.15*N))` or greater |
| `attempt_id`, `parent_attempt_id`, `delegated_by` | parent edge | delegated object carries exact parent thread/call IDs |
| `role`, `kind`, `depth`, `wave` | routing/ownership | coordinator depth 1; leaf depth 2 |
| lifecycle/recovery fields | timestamps, TTL, retry, epoch, dedup, cancel | every attempt is counted and auditable |
| child/result/runtime fields | planned/collected IDs, thread/turn receipts | acceptance requires exact completed turn and parent provenance |

## Minimal planning example

```json
{
  "ledger_type": "project",
  "version": 2,
  "tree_id": "550e8400-e29b-41d4-a716-446655440100",
  "run_id": "550e8400-e29b-41d4-a716-446655440101",
  "mode": "flat",
  "phase": "planning",
  "closure_status": "open",
  "N": 4,
  "attempt_budget_N": 4,
  "concurrency_cap_C": 8,
  "wave_width_W": 4,
  "max_workflow_depth": 2,
  "verifier_reserve_V": 1,
  "verifier_reserve": 1,
  "overall_deadline": "2026-08-16T18:00:00+09:00",
  "root_integration_status": "not_started",
  "root_integration_receipt": null,
  "target_gate": "LOCAL_PASS",
  "verified_gates": [],
  "gate_receipts": {},
  "external_authority": false,
  "assignments": [
    {
      "attempt_id": "P-01",
      "parent_attempt_id": null,
      "delegated_by": {"parent_attempt_id": null, "parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440110", "parent_call_id": "call-root-p01"},
      "root_parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440110",
      "root_parent_call_id": "call-root-p01",
      "depth": 1,
      "wave": 1,
      "planned_at": "2026-08-16T17:00:00+09:00",
      "started_at": null,
      "finished_at": null,
      "retry_of": null,
      "descendant_budget": 0,
      "planned_child_attempt_ids": [],
      "collected_result_ids": [],
      "may_spawn_descendants": false,
      "ttl_seconds": 1800,
      "epoch": 1,
      "retry_owner": "root",
      "dedup_key": "component-a",
      "cancel_reason": null,
      "kind": "builder",
      "role": "builder",
      "objective": "Produce one isolated candidate for component A",
      "ownership": ["src/component_a"],
      "dependencies": [],
      "deadline": "2026-08-16T17:20:00+09:00",
      "execution_status": "planned",
      "acceptance_status": "pending",
      "acceptance_criteria": ["focused tests pass", "candidate diff is inspectable"],
      "evidence_locator": "pending:P-01",
      "integration_status": "pending",
      "thread_uuid": null,
      "child_thread_uuid": null,
      "runtime_turn": null,
      "agent_role": null,
      "runtime_model": null,
      "runtime_effort": null,
      "parent_thread_uuid": null,
      "parent_call_id": null,
      "spawn_kind": null,
      "safety_enforcement": "unknown",
      "runtime_verified": false
    },
    {
      "attempt_id": "P-02",
      "parent_attempt_id": null,
      "delegated_by": {"parent_attempt_id": null, "parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440110", "parent_call_id": "call-root-p02"},
      "root_parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440110",
      "root_parent_call_id": "call-root-p02",
      "depth": 1,
      "wave": 1,
      "planned_at": "2026-08-16T17:00:00+09:00",
      "started_at": null,
      "finished_at": null,
      "retry_of": null,
      "descendant_budget": 0,
      "planned_child_attempt_ids": [],
      "collected_result_ids": [],
      "may_spawn_descendants": false,
      "ttl_seconds": 1800,
      "epoch": 1,
      "retry_owner": "root",
      "dedup_key": "integrated-verification",
      "cancel_reason": null,
      "kind": "verifier",
      "role": "verifier",
      "objective": "Verify the integrated result against the contract",
      "ownership": ["read-only"],
      "dependencies": ["P-01"],
      "deadline": "2026-08-16T17:50:00+09:00",
      "execution_status": "planned",
      "acceptance_status": "pending",
      "acceptance_criteria": ["all criteria have exact evidence or a blocker"],
      "evidence_locator": "pending:P-02",
      "integration_status": "not_applicable",
      "thread_uuid": null,
      "child_thread_uuid": null,
      "runtime_turn": null,
      "agent_role": null,
      "runtime_model": null,
      "runtime_effort": null,
      "parent_thread_uuid": null,
      "parent_call_id": null,
      "spawn_kind": null,
      "safety_enforcement": "unknown",
      "runtime_verified": false
    }
  ]
}
```

## Validation points

Run at planning, immediately before integration, and again at closure:

```text
python <skill-dir>/scripts/check_setup.py --agent-role <selected-role> --ledger-json <project-ledger.json>
```

At integration and closure, add `--verify-ledger-receipts`. It reopens every accepted child turn and its unique parent `spawn_agent` request. Complete closure requires no unfinished row, at least the reserved number of accepted verifiers, completed root integration with a receipt, every accepted builder/operator marked integrated, and the target evidence gate present in the verified contiguous prefix.
