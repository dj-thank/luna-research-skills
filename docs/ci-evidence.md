# Check required CI evidence

A watcher finishing successfully does not establish that every required check
succeeded. During repository maintenance, `gh pr checks --watch` exited zero while
a required job was cancelled before any steps. An individual check-run readback
caught it before merging. The [CLI manual](https://cli.github.com/manual/gh_pr_checks)
distinguishes pass, failure, pending, skipped and cancelled buckets.

`tools/check_ci_snapshot.py` checks a saved GitHub check-run response against a
separate trusted policy. It is offline and read-only, and ships in both the source
archive and plugin. It does not fetch credentials, rerun CI, merge or deploy.

## Try the synthetic example

From an extracted source archive or plugin, use Python 3.11+. On Windows substitute
`py -3` for `python` if needed; on macOS/Linux use `python3`.

```sh
python tools/check_ci_snapshot.py --policy tools/fixtures/ci_policy.json --snapshot tools/fixtures/ci_snapshot.json
```

The [example policy](../tools/fixtures/ci_policy.json) and
[snapshot](../tools/fixtures/ci_snapshot.json) are synthetic: their commit, app and
run IDs are placeholders. The command returns JSON with `passes_required_checks`,
per-check diagnostics and SHA-256 fingerprints of the two input files.

## Supply an independent policy and a fresh response

1. Fix the expected full commit SHA and required checks from your trusted task,
   workflow and repository policy. Choose the appropriate PR or post-merge context.
   Never infer the required list from whichever checks happen to be present.
2. Read the [check runs for that exact Git reference](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference)
   through your authenticated provider connection. Use `filter=latest`, without
   `status`, `check_name` or `app_id` filters. Include every page. Preserve the
   response and its retrieval context outside the public repository.
3. Run the checker. A count mismatch means the supplied snapshot cannot support
   completion. Resolve duplicate required name/app pairs through provider readback;
   do not select an arbitrary successful result or the largest ID.
4. Before acting, confirm the head is still current, obtain a fresh provider
   readback, and satisfy the repository's protection, review and approval rules.
   For an authorized merge, retain an exact-head guard such as
   `gh pr merge --match-head-commit EXPECTED_SHA`.

The policy has exactly these fields:

```json
{
  "schema_version": 1,
  "expected_head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "required_checks": [
    {"name": "unit tests", "app_id": 42},
    {"name": "lint", "app_id": 42}
  ]
}
```

Each name/app pair must be unique. Names match exactly; app IDs are positive
integers. A differently named check or one from another app cannot satisfy a
requirement. Distinct apps can intentionally have the same required name.

The snapshot uses the REST response's `total_count` and `check_runs` array. Each
run needs `id`, `name`, `head_sha`, `app.id`, `status`, and `conclusion`. Unused API
fields are allowed. All run IDs must be unique and all rows must belong to the
expected full SHA. The declared count must equal the supplied row count. If
combining pages, verify consistent counts and identities; restart the read if the
provider changes during collection. A forged count cannot prove page completeness.

Every required name/app pair must appear **exactly once**, with status `completed`
and conclusion `success`. Missing, ambiguous, nonterminal or non-successful
required runs block the result. Other checks may fail or remain pending without
changing this narrow required-set result. Invalid types, missing identity metadata,
duplicate JSON keys and duplicate run IDs are input errors.

| Exit | Meaning |
| --- | --- |
| `0` | The supplied snapshot satisfies the trusted local required-check policy |
| `1` | The snapshot is incomplete, ambiguous, stale for the expected SHA, or has an unmet required check |
| `2` | Invalid arguments, unreadable files or malformed input |

## Limits and GitHub semantics

This is a **success-only evidence rule**, intentionally stricter than GitHub's
merge eligibility: GitHub can accept `neutral` and `skipped` checks. Its choice of
head versus test-merge SHA and workflow event also matters. See
[GitHub's required-check troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).
Do not use this tool as a complete implementation of GitHub branch protection.

The tool accepts check-run responses, not legacy commit statuses, `gh pr checks`
arrays, workflow summaries or merge-queue approval records. A matching app ID in a
local JSON file is a claim until its provider origin is verified. The tool cannot
prove freshness, retrieve omitted runs, detect forged counts, prove tests really
ran, or validate the caller's chosen requirements. A SHA-256 fingerprint binds
the bytes inspected; it authenticates neither their source nor permission to act.

Development froze 34 controls before implementation, including the observed
cancelled PR and successful main receipts. All seven valid snapshots passed;
all 27 invalid or insufficient ones were refused. An explicit exit-code-only
ablation incorrectly accepted 27 and rejected one. That ablation was not the
repository's existing acceptance workflow, which already reread individual
checks. These are bounded controls, not a detection rate for unseen providers.
