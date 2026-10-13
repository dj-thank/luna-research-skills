# Select coordinator and specialist models explicitly

Read when choosing a recursive team or when the current Luna role does not expose
child-spawn tools. This contract adds a model composition option; it does not add
native tools to a model or change the parent task's model.

## Default: Luna throughout the delegated lane

Without `coordinator_model_policy`, all accepted coordinators and terminal specialists
remain `gpt-6-luna` with `low` effort. A missing child-spawn tool closes that branch
with an explicit capability gap. Root can dispatch its remaining work flat within
the original budget. Never silently select another model.

## Explicit Sol profile

When the user explicitly asks for Sol specialists, preserve that request and use
`model="gpt-6.1-sol"`, `reasoning_effort="low"` with the same fresh-context route,
ownership, receipt checks and N/C/W/V budget. Select the same model explicitly
when checking each receipt or a complete ledger:

```text
python <skill-dir>/scripts/check_setup.py --specialist-model gpt-6.1-sol --agent-role default --allow-generic-worker --runtime-rollout <actual-child.jsonl> --runtime-turn <completed-turn-uuid> --parent-rollout <actual-parent.jsonl> --require-spawn-provenance
```

For complete ledger verification, retain `--specialist-model gpt-6.1-sol` with
`--ledger-json` and `--verify-ledger-receipts`. The switch changes the expected
model of terminal specialists, static role checks and parent-edge checks together.
It does not rewrite configuration or select Sol automatically. Without the switch,
a Sol child cannot pass as a Luna child; with it, a Luna child cannot pass as Sol.

The selected terminal profile also applies to an explicitly authorized Astra
coordinator composition. An alternative terminal model needs a supported explicit
profile; changing a nickname or a ledger's claimed model cannot change acceptance.

## Opt-in: Astra coordinators with Luna specialists

Use this composition only when the user's instruction authorizes it. A coordinator
may use `gpt-6-astra` while terminal researchers, builders, reviewers and verifiers
remain Luna/low. Coordinators partition work, create smaller teams, collect results
and relay corrections. They do not replace a terminal specialist by changing its
label to coordinator.

Declare the policy once at the top level of the version-2 ledger:

```json
{
  "coordinator_model_policy": {
    "model": "gpt-6-astra",
    "reasoning_effort": "high"
  }
}
```

This is a field to add to a complete ledger, not a runnable ledger by itself. `high`
is an example: preserve the agreed coordinator effort and verify the actual runtime.
The current explicit policy accepts Astra's exposed low/medium/high/xhigh/max/ultra
settings, or Luna/low as the unchanged policy. Unknown models, unsupported efforts,
extra keys, row-local policies and nested conflicting copies are rejected.

Use an exposed generic `default` route with the declared model, or built-in `worker`
with explicit model/effort and fresh context. Model-fixed custom roles may override the
requested model; use generic worker/default as the standard route. Check
native spawn capability at every newly used level before widening the team.

Final mixed acceptance requires an explicit CLI opt-in as well as the ledger policy:

```text
python <skill-dir>/scripts/check_setup.py --agent-role worker --allow-generic-worker --allow-mixed-coordinators --ledger-json <ledger.json> --verify-ledger-receipts
```

The worker option remains necessary when worker is the chosen route. Planning may
describe the composition, but non-Luna coordinator acceptance without the mixed
option fails. That option applies only to a logical coordinator with explicit
delegation permission and real child spawns. Terminal records still require Luna/low.
The checker reopens exact child turns and parent calls, and checks model/effort and
depth rather than accepting a model name supplied only in the ledger. Collection
sets and ordering are checked for ledger consistency; root must inspect the actual
messages/results to confirm collection. A non-empty collection receipt alone does
not prove that the result was received or read.

## Describe the result accurately

Report the models that actually ran by role. A mixed pass is not a Luna-only pass.
A native Astra chain demonstrates that tested Astra surface; it does not prove that
Luna can recursively spawn. A synthetic mixed ledger tests validation behavior,
not execution. Keep these distinctions in the dated method/evaluation receipt.
