# Check the current execution environment

Use this reference when first checking a Windows runtime, when a command fails,
or when a native CLI feature listing contradicts the saved configuration or live tools.
This is a diagnostic path, not authorization to launch a full workflow.

## Keep the execution surfaces separate

Record the selected absolute skill path, checker version, Python executable,
current root thread, saved `[agents]` and feature settings, and live spawn declaration.
Check `python -c "import sys; print(sys.executable)"` in the same execution surface
that will run the checks. Use Python 3.11 or later.

A Windows sandbox can execute a native CLI or Python as a different account,
with a different home, PATH, installed packages, and readable files. An empty
`CODEX_HOME` does not establish which home a separate native process used.
If `codex features list` disagrees with the caller's saved setting, compare the
exact executable/version and execution account before diagnosing disabled V2.
An authorized read-only check in the normal host can settle that discrepancy.
Keep both results; do not change valid global settings to repair a subprocess's view.
The caller's exposed tools and its completed child receipts establish that caller's
capabilities. A different CLI run neither proves nor disproves them.

## Validate the common route, then its actual completion

The commands below illustrate a V2 check. Include `--require-v2` only when that
run promises V2; otherwise omit it. This diagnostic does not add a V2 entry gate.

Resolve `<skill-dir>` to the selected installed package. Check setup with:

```text
python <skill-dir>/scripts/check_setup.py --agent-role default --allow-generic-worker --require-v2
```

Supply `--spawn-schema-json <schema.json>` when an accurately recorded live
declaration is available. Label a manual transcription as such; retain unconstrained
fields and do not invent enums. Static READY is preparation, not completed execution.
Before a useful child is launched, run the objective's trace preflight from
[parent efficiency](parent-efficiency.md#dispatch-limits-and-trace-preflight).
Use the current native tool directly with the explicit fresh-context route and
Sol/low values. A fixed-model historical Luna custom role can override requested
model values; it is not the standard generic `default` / `worker` route.

After the initial child turn completes, run:

```text
python <skill-dir>/scripts/check_setup.py --agent-role default --allow-generic-worker --require-v2 --runtime-thread <child-uuid> --runtime-turn <completed-turn-uuid> --parent-rollout <actual-root.jsonl> --require-spawn-provenance
```

Find the child through its actual `source.subagent.thread_spawn` metadata and
parent edge. A guardian or another system-created child is not the delegated worker.
Do not claim read-only access from a no-mutation prompt: record the effective sandbox.
One common-route test proves that route and bounded assignment, not a complete
Research or Project run. Full runs still require their packet, ledger and closure checks.

## Package validation prerequisites

The bundled Skill Creator `quick_validate.py` imports PyYAML. The route checker
and regression suites use the standard library; their success does not prove that
the package validator's dependency is present. Check `yaml.safe_load`, not just
`import yaml`: an unreadable package directory can import as a namespace module.

```text
python -c "import yaml; assert callable(getattr(yaml, 'safe_load', None)); print(yaml.__file__)"
```

When needed, place validation dependencies under this task's `work` directory and
set process-local `PYTHONPATH` for the validator. Use the same interpreter and
execution account for installation and validation. Network or filesystem approval
remains action-specific. An approved host-side installation may be unreadable to the
sandbox account; diagnose the exact boundary and run the authorized validation in
the matching surface. Do not reinstall globally, replace the validator with a mock,
or claim success until the real validator passes.
