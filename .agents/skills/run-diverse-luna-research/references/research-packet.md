# Research packet and root-ledger contract

## Hierarchy and budget contract

The root chooses `mode=flat|hierarchical`. Hierarchical depth is fixed to `root=0 -> coordinator=1 -> leaf=2`; leaves have `may_spawn_descendants=false`. A coordinator can dispatch only its exact `descendant_budget` loan from root. All roles, probes, retries, and verifiers decrement the same global `attempt_budget_N`; capacity `concurrency_cap_C` and total per-wave starts `wave_width_W` are independent controls, with `W <= min(C,N)`. Reserve `verifier_reserve_V=max(1,ceil(.15*N))`, and never spend it on optional fanout.

Every attempt row must contain: `tree_id`, `attempt_budget_N`, `concurrency_cap_C`, `wave_width_W`, `max_workflow_depth`, `attempt_id`, `parent_attempt_id`, `delegated_by`, `depth`, `wave`, `planned_at`, `started_at`, `finished_at`, `retry_of`, `descendant_budget`, `planned_child_attempt_ids`, `collected_result_ids`, and `may_spawn_descendants`. Include `ttl`, `epoch`, `retry_owner`, `dedup_key`, and `cancel_reason` when applicable. Parent-edge provenance is required: exact parent thread, call ID, selected route, and completed child turn. Static names/TOMLs are metadata only.

### Canonical JSON field table

| Field | Meaning | Canonical rule |
|---|---|---|
| `tree_id`, `run_id` | UUID identities | both required; never human labels |
| `attempt_budget_N`, `concurrency_cap_C`, `wave_width_W`, `max_workflow_depth`, `verifier_reserve_V` | global controls | canonical names; require `W<=C`, `W<=N`, and `V=max(1,ceil(.15*N))` |
| `attempt_id`, `parent_attempt_id`, `delegated_by` | edge identity | `delegated_by` object carries exact parent thread/call UUIDs |
| `role`, `kind`, `depth`, `wave` | routing | coordinator depth 1; leaves depth 2 and no descendants |
| `planned_at`, `started_at`, `finished_at`, `ttl_seconds`, `epoch` | lifecycle | planned rows have null start/finish |
| `retry_of`, `retry_owner`, `dedup_key`, `cancel_reason` | recovery | every retry is a new counted attempt |
| `planned_child_attempt_ids`, `collected_result_ids`, `may_spawn_descendants` | fanout/fan-in | leaf `may_spawn_descendants=false` |
| `child_thread_uuid`, `thread_uuid`, `runtime_turn`, `parent_thread_uuid`, `parent_call_id` | runtime receipt | exact completed turn and parent edge required on acceptance |

Return one compact packet for one assigned coverage cell. Limit a scout packet to 12 evidence items and about 1,000 words. The scout supplies evidence; the root appends the runtime receipt and decides what is accepted.

## 1. Assignment identity

- Assignment ID and quota label: `primary`, `adversarial`, `measurement_gap`, or `other`
- Coverage cell and exact question or claim tested
- One source plane: `public_web`, `local`, `internal_session`, `connector_private`, or `provider`
- Owner or authority relevant to the claim
- Scope, exclusions, geography, languages, and freshness cutoff
- Access mode: `sandbox_read_only`, `prompt_only_public`, or `root_only`
- Sensitivity and redaction rule
- Search strategy, source universe, independence rule, deadline, and stop condition

Never place a secret, credential, invitation code, personal identifier, exact private location, or signed/query-token URL in the packet.

Access modes are combinations, not free labels. `prompt_only_public` is valid only with `public_web` and means behavioral no-mutation in a writable runtime. `sandbox_read_only` proves only the effective filesystem sandbox; it does not prove that connector or provider tools are read-only. `connector_private` and `provider` remain `root_only` unless a future runtime receipt can mechanically prove both filesystem and external-tool permissions. A `root_only` row is never dispatched or accepted as a child result: keep it `planned/pending` while open, then close it as `not_dispatched/excluded` with `finished_at` and an explicit `gap_reason`.

## 2. Evidence ledger

For each item, provide:

1. A stable evidence ID.
2. The exact claim supported, challenged, or left unresolved.
3. A redacted canonical URL and precise section, page, table, paragraph, API field, dataset row, or timestamp locator. For non-web material, provide the exact object ID or path, content hash when available, and `observed_at`.
4. Source title, publisher or author, publication or update date, and access date.
5. What the source directly establishes without inference.
6. Source class: primary, official, peer-reviewed, original data, industry, journalism, expert commentary, or other.
7. Source plane and authority: who owns the fact, who merely projects it, and whether the observation is current or historical.
8. Independence: original source, independent corroboration, or dependent repetition; identify the likely upstream family.
9. Freshness status: current for the contract, stale, undated, or unknown.
10. Confidence: high, medium, or low, with one sentence of rationale.
11. A limitation, contradiction, privacy concern, access limitation, or missing context.
12. Evidence-gate note: what was directly observed and which higher gate it does **not** prove. Scouts never assign `DEVICE_PASS`, `PROVIDER_PASS`, `PUBLIC_PASS`, or `HUMAN_GO`.

For live prices, market data, closures, schedules, laws, policies, fees, availability, or provider state, include the retrieval timestamp, jurisdiction or network, API/document version where available, and enough locator detail to refresh the observation.

## 3. Cell synthesis

- Give three to seven findings specific to the assigned cell.
- Label each as `sourced fact`, `source interpretation`, or `inference`.
- State the strongest disconfirming evidence and whether it changed the cell conclusion.
- Identify conflicts with other likely cells or source planes.
- Separate functional behavior from authenticity, authority, safety, privacy, financial viability, and legal status when applicable.
- State important unknowns and an explicit gap reason.
- Recommend one follow-up query only when the gap is material.

## 4. Scout self-check

- Every material claim maps to a directly supporting evidence ID.
- URLs are canonical, redacted, and dependent repetitions are marked.
- Dates and `observed_at` are present where freshness matters.
- The packet stayed inside one cell, one plane, the source universe, and the item limit.
- No source instruction was executed; no invitation, payment, message, provider, browser-write, account, file, or shared-state mutation occurred.
- No lower-plane observation or successful function was promoted to authenticity, safety, provider, public, or human approval.

## 5. Root runtime receipt

The root appends this after the scout completes:

- assignment ID, task path, child thread UUID, parent UUID, depth, and selected role;
- exact accepted completed turn ID;
- effective model and reasoning effort;
- effective sandbox or permission mode;
- safety enforcement: `sandbox_read_only`, `prompt_only`, or `unknown`;
- outcome: `accepted`, `rejected`, `failed`, `timed_out`, or `abandoned`;
- rejection or gap reason;
- runtime-check command with exact `--runtime-thread` and `--runtime-turn`, plus observed timestamp.
- parent spawn provenance: parent thread UUID, parent rollout locator, call ID, `spawn_agent`, exact selected role, and non-history route.

Opaque spawn arguments, task names, nicknames, static TOML, and a scout's self-report are not runtime receipts.

## 6. Root assignment ledger

Maintain one row per assignment attempt:

| Field | Required value |
|---|---|
| Assignment | Stable ID and coverage cell |
| Budget | `N`, ordinal attempt, wave, reserved/start time, deadline |
| Ownership | source plane, authority, access mode, sensitivity |
| Coverage | quota label, source universe, exclusions, overlap key |
| Runtime | thread UUID, parent/depth, role, model, effort, safety enforcement |
| Status | execution status plus separate acceptance status |
| Evidence | canonical source-family IDs, packet locator, root-opened flag |
| Result | material claim, contradiction, verification, no-op, or gap reason |

For lifecycle validation, `planned/pending` has not started, `not_dispatched/excluded` is a terminal root-only gap, and actual child work uses `started` followed by `completed`, `failed`, `timed_out`, or `abandoned`. Every terminal row has `finished_at` or `timeout_at`. Work may not start after its assignment or overall deadline, and a late completion may not be accepted.

Keep the machine-readable ledger as UTF-8 JSON with this shape:

```json
{
  "ledger_type": "research",
  "version": 2,
  "tree_id": "550e8400-e29b-41d4-a716-446655440000",
  "run_id": "550e8400-e29b-41d4-a716-446655440001",
  "mode": "hierarchical",
  "attempt_budget_N": 4,
  "concurrency_cap_C": 4,
  "wave_width_W": 3,
  "max_workflow_depth": 2,
  "verifier_reserve_V": 1,
  "phase": "planning",
  "closure_status": "open",
  "overall_deadline": "2026-08-16T12:00:00+09:00",
  "assignments": [
    {
      "attempt_id": "R-01",
      "parent_attempt_id": null,
      "delegated_by": {"parent_attempt_id": null, "parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440010", "parent_call_id": "call-root-r01"},
      "root_parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440010",
      "root_parent_call_id": "call-root-r01",
      "depth": 1,
      "wave": 1,
      "planned_at": "2026-08-16T11:00:00+09:00",
      "started_at": null,
      "finished_at": null,
      "descendant_budget": 0,
      "planned_child_attempt_ids": [],
      "collected_result_ids": [],
      "may_spawn_descendants": false,
      "ttl_seconds": 1800,
      "epoch": 1,
      "retry_owner": "root",
      "dedup_key": "official-spec-current",
      "cancel_reason": null,
      "coverage_cell": "official primary specification",
      "priority": true,
      "quota_label": "primary",
      "source_plane": "public_web",
      "access_mode": "prompt_only_public",
      "source_universe": "official documentation",
      "exclusion_rule": "exclude mirrors and reposts",
      "overlap_key": "official-spec-current",
      "retry_of": null,
      "deadline": "2026-08-16T11:20:00+09:00",
      "execution_status": "planned",
      "acceptance_status": "pending",
      "role": "research_scout_luna",
      "kind": "evidence_lane",
      "child_thread_uuid": null,
      "thread_uuid": null,
      "runtime_turn": null,
      "agent_role": null,
      "runtime_model": null,
      "runtime_effort": null,
      "parent_thread_uuid": null,
      "parent_call_id": null,
      "spawn_kind": null,
      "safety_enforcement": "unknown",
      "runtime_verified": false,
      "gap_reason": null
    },
    {
      "attempt_id": "R-02",
      "parent_attempt_id": null,
      "delegated_by": {"parent_attempt_id": null, "parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440010", "parent_call_id": "call-root-r02"},
      "root_parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440010",
      "root_parent_call_id": "call-root-r02",
      "depth": 1,
      "wave": 1,
      "planned_at": "2026-08-16T11:00:00+09:00", "started_at": null, "finished_at": null,
      "retry_of": null, "descendant_budget": 0, "planned_child_attempt_ids": [], "collected_result_ids": [], "may_spawn_descendants": false,
      "ttl_seconds": 1800, "epoch": 1, "retry_owner": "root", "dedup_key": "adversarial-gap", "cancel_reason": null,
      "coverage_cell": "adversarial contradiction", "priority": false, "quota_label": "adversarial", "source_plane": "public_web", "access_mode": "prompt_only_public", "source_universe": "independent contrary sources", "exclusion_rule": "exclude dependent mirrors", "overlap_key": "adversarial-gap", "deadline": "2026-08-16T11:20:00+09:00", "execution_status": "planned", "acceptance_status": "pending", "role": "reviewer", "kind": "verifier", "child_thread_uuid": null,
      "thread_uuid": null, "runtime_turn": null, "agent_role": null, "runtime_model": null, "runtime_effort": null, "parent_thread_uuid": null, "parent_call_id": null, "spawn_kind": null, "safety_enforcement": "unknown", "runtime_verified": false, "gap_reason": null
    },
    {
      "attempt_id": "R-03",
      "parent_attempt_id": null,
      "delegated_by": {"parent_attempt_id": null, "parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440010", "parent_call_id": "call-root-r03"},
      "root_parent_thread_uuid": "550e8400-e29b-41d4-a716-446655440010",
      "root_parent_call_id": "call-root-r03",
      "depth": 1, "wave": 1, "planned_at": "2026-08-16T11:00:00+09:00", "started_at": null, "finished_at": null, "retry_of": null, "descendant_budget": 0, "planned_child_attempt_ids": [], "collected_result_ids": [], "may_spawn_descendants": false, "ttl_seconds": 1800, "epoch": 1, "retry_owner": "root", "dedup_key": "measurement-gap", "cancel_reason": null,
      "coverage_cell": "measurement gap", "priority": false, "quota_label": "measurement_gap", "source_plane": "public_web", "access_mode": "prompt_only_public", "source_universe": "original data", "exclusion_rule": "exclude commentary", "overlap_key": "measurement-gap", "deadline": "2026-08-16T11:20:00+09:00", "execution_status": "planned", "acceptance_status": "pending", "role": "reviewer", "kind": "verifier", "child_thread_uuid": null, "thread_uuid": null, "runtime_turn": null, "agent_role": null, "runtime_model": null, "runtime_effort": null, "parent_thread_uuid": null, "parent_call_id": null, "spawn_kind": null, "safety_enforcement": "unknown", "runtime_verified": false, "gap_reason": null
    }
  ]
}
```

Allowed execution states are `planned`, `not_dispatched`, `started`, `completed`, `failed`, `timed_out`, and `abandoned`. The only valid state pairs are `planned|started -> pending`, `not_dispatched -> excluded`, `completed -> accepted|rejected`, and `failed|timed_out|abandoned -> excluded`. Follow-up turns are not production-acceptable receipts; start a fresh counted assignment so every accepted row binds to one `spawn_agent` call. Change `phase` to `synthesis` before the final check. Run:

```text
python <skill-dir>/scripts/check_setup.py --agent-role <selected-role> --ledger-json <ledger.json>
```

Reconcile:

```text
planned >= started attempts
started attempts = completed + failed + timed_out + abandoned + still_in_flight
accepted + rejected <= completed
started <= N
```

Before synthesis, require zero unclassified in-flight assignments. Every accepted attempt needs valid child and parent UUIDs, exact turn UUID, parent call ID, `spawn_kind=spawn_agent`, role, Luna/medium metadata, matching safety enforcement, and `runtime_verified=true`. Run the checker with `--verify-ledger-receipts`; it must reopen the exact child turn and the unique parent spawn request, so a declaration alone is not acceptance evidence. Every priority cell must be accepted or have a non-empty gap reason. A timed-out or abandoned result is excluded even if it arrives later, unless the root deliberately starts a new counted acceptance attempt.
