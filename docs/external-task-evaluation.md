# Test a handoff on an actual external repair task

The source checkout includes an executable [task probe](https://github.com/dj-thank/luna-research-skills/blob/main/examples/value_chain_task/probe.py), a [fixed contract](https://github.com/dj-thank/luna-research-skills/blob/main/examples/value_chain_task/contract.json), two patches and compact actual receipts. These source-only examples are not included in the plugin ZIP. No new reader or automatic acceptance service is added.

## Task and fixed obligations

[more-itertools issue 1250](https://github.com/more-itertools/more-itertools/issues/1250) reports that `value_chain` swallows a `TypeError` raised while consuming an iterable. The returned stream then contains the partially consumed iterator itself. We checked out upstream commit `bc8be1013ac90fe3c1df8aae646b02605d578818` in a separate workspace, read its API and tests, and fixed 12 behavior obligations before executing any variant:

- Four repair tests: a failing `map`, a generator failing before its first value, a generator failing after a prefix, and an iterator failing in `__next__`. Check the already-yielded prefix and original exception identity where applicable.
- Eight preservation tests: empty inputs, scalar values, text/bytes, one-level flattening, mapping order, an object whose `__iter__` rejects iteration, laziness and other exception types.

The [SWE-bench paper, Appendix A.4/A.5](https://arxiv.org/html/2310.06770v3#A4) separates repaired behavior from preserved behavior and requires every required test to be present and pass. We applied that distinction to this one task. This is **not an official SWE-bench instance or score**.

## Execute, find a regression, repair, verify

These are actual executions of three complete upstream checkouts, not simulated test statuses:

| Code variant | Repair tests | Preservation tests | Original upstream suite |
|---|---:|---:|---:|
| Original pinned code | 0/4 | 8/8 | 905 passed |
| Remove the exception handler (deliberate negative control) | 4/4 | 6/8 | Not run |
| Classify with `iter()`, then consume outside the handler | 4/4 | 8/8 | 905 passed |

The negative control breaks scalar handling and the classification-error behavior. It is retained as a rejected candidate. The final patch catches only the attempt to obtain an iterator; exceptions during consumption propagate.

The 12-test comparison and both upstream suites ran on **Windows / CPython 3.12.10**. The final 12-test probe also passed on **Windows / CPython 3.11.15**. Repository CI checks the saved handoff example on its usual OS/Python matrix; it does not rerun the external repository or establish its behavior on other operating systems.

## Reproduce with a source checkout

Run from this repository's root using Python 3.11 or newer. The probe **imports and executes the supplied checkout**: use a reviewed, trusted source. It downloads, installs and edits nothing; it writes its JSON result to stdout and disables bytecode writes. Start with unused workspace paths.

```sh
git clone --no-checkout https://github.com/more-itertools/more-itertools.git work/value-chain-base
git -C work/value-chain-base checkout --detach bc8be1013ac90fe3c1df8aae646b02605d578818
python examples/value_chain_task/probe.py --repo work/value-chain-base
```

Expected: 4 `FAIL`, 8 `PASS`, exit **1**. Each result contains the actual source SHA256, Python version and individual test outcomes. Line endings can change source hashes across checkouts; retain the hash of the bytes actually executed.

Create separate candidates and apply the supplied patches:

```sh
git -C work/value-chain-base worktree add --detach ../value-chain-negative bc8be1013ac90fe3c1df8aae646b02605d578818
git -C work/value-chain-negative apply ../../examples/value_chain_task/negative-control.patch
python examples/value_chain_task/probe.py --repo work/value-chain-negative
git -C work/value-chain-base worktree add --detach ../value-chain-fixed bc8be1013ac90fe3c1df8aae646b02605d578818
git -C work/value-chain-fixed apply ../../examples/value_chain_task/fix.patch
python examples/value_chain_task/probe.py --repo work/value-chain-fixed
```

Negative control: 10 `PASS`, 2 `ERROR`, exit **1**. Fixed: 12 `PASS`, exit **0**. The error outcomes are real exceptions in the two preservation tests, not missing tests. Run the original suite in the fixed checkout:

```sh
cd work/value-chain-fixed
python -m unittest discover -s tests
cd ../..
```

Expected on the recorded environment: 905 tests, exit 0. The source example includes upstream's MIT notice for the patch context.

## Compare the handoff, using the same real receipts

Both questions bind the exact source and probe hashes and require all repair tests. The complete question also requires every preservation test to appear in `passed_ids`. It uses the existing [requirement reader](requirement-selection.md); the source bytes, facts, failures and qualifiers are the same in both arms.

```sh
python tools/read_requirements.py --question examples/value_chain_task/regression-narrow.json --sha256 df85e34b5afcf85403d6292c0578d3912c2d6398d41d7eaf07449cc238d9d8ee --source examples/value_chain_task/regression-source.json
python tools/read_requirements.py --question examples/value_chain_task/regression-complete.json --sha256 b95cb5f1b3b3acb008aa7514ed768c6a37151d875190f235563d01360bdf4584 --source examples/value_chain_task/regression-source.json
python tools/read_requirements.py --question examples/value_chain_task/fixed-complete.json --sha256 0642adb71b9d9617411ae2c18ef040dd174fdb0a7128e3c9f4bb09d7b50d0ccd --source examples/value_chain_task/fixed-source.json
```

Expected exits are **0, 1, 0**, respectively. The narrow question returns `OBSERVED` even for the negative control because all *declared* checks match. Its returned facts still show both errors; that status never meant task completion. The complete question returns `existing-behavior: MISMATCH`, with no partial observations. The fixed candidate satisfies both.

Two additional **synthetic receipt-corruption controls**, kept separate from the real code executions, substitute the negative control's receipt for the final source or omit a required test. The complete question rejects both. Tests of missing coverage must fail closed; unreported and skipped cases are not passes.

All five comparisons use one source read per arm, with identical source bytes. For the valid final view, question bytes rise **932 → 1,097** and response bytes **2,745 → 2,810**. Every original record and qualifier is retained. This is extra diagnostic coverage with a small measured byte overhead, not demonstrated speed, cost or model-quality improvement.

## Use the result in the next task

1. Define both the desired change and existing behavior that must survive, before editing code. Freeze identifiable tests and expected outcomes; review the oracle separately from the test generator.
2. Run the original code. Preserve both its failing new tests and its passing regression tests. A green existing suite alone may miss the reported bug.
3. Keep each attempted patch and its actual outcomes. Require every declared repair **and** preservation test to pass; do not discard a regression to improve the score.
4. Bind the handoff to the executed source and test bytes, and check required test IDs against passed IDs. Keep failures, scope and provenance visible.
5. Run the project's required broader checks before adoption, then inspect original logs and implementation. This example checks one changed source file; real multi-file tasks must bind the full candidate and relevant dependencies.

Source/receipt equality does not authenticate a fabricated result, discover missing requirements or prove upstream approval. The broader suite remains a separate root acceptance gate. No upstream PR was sent; all external changes are isolated local artifacts.

Root authored and ran this experiment after the objective's native delegation budget reached 6/6. The issue already disclosed a suggested fix and root read it. There was **no blind solve, fresh independent agent review or agent-versus-agent experiment**. The result generalizes only as a procedure to test on further tasks, not a measured success rate.

Frozen X33 record SHA256: `a8cff5e522805c1ca0ed0df4f644cce2d2d093f296f0fcdd997748568e8c222e`. The [compact results](https://github.com/dj-thank/luna-research-skills/blob/main/examples/value_chain_task/results.json) retain every test ID/status and the rejected candidate. Raw local logs and original failures remain in the workspace.
