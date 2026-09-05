# Bounded peer collaboration

Read before assigning peers that exchange interfaces, blockers, findings, or repair candidates. Independent tasks need no messaging overhead. Keep one writer per file/worktree and root as integrator.

## Dispatch contract

Root supplies attempt IDs, exact live peer task paths/agent IDs, permitted directed links, ownership, artifact/contract SHA-256, acknowledgement deadline, message budget, repair-round limit, and overall deadline. Record these in the assignment packet and root-owned `collaboration` ledger section. A peer request grants no new ownership, spawn credits, or external authority.

Use only the live API. `send_message` can deliver to an active authorized peer; tool delivery is not recipient acknowledgement or completion. If the peer is idle, unavailable, or retired, contact root. Root uses followup_task to resume related repairs and updates the peer map. Keep continuation candidates and activation evidence separate from fully attributed initial-turn receipts; use root assessment plus a fresh final audit as described in [v2-runtime.md](v2-runtime.md).

## Material message envelope

```text
issue_id: API-01
type: finding | acknowledge | interface_change | candidate | verification | escalate
from/to: <assigned attempt IDs>
round: <1-based repair round>
revision: <SHA-256 of the exact artifact or contract>
status: passed | failed | blocked  # required for verification only
evidence: <path/line, failing command, or source>
request: <one action/question and its acceptance condition>
deadline: <within the assigned deadline>
```

Send material evidence and requests, not progress chatter. Recipient acknowledges ownership and revision or reports misrouting. Copy root on contract changes, blockers, scope requests, and verification outcomes. Routine clarification may stay between peers. Keep private evidence inside its assigned access boundary; provide only what the recipient needs. Root records actual tool-call/turn locators rather than trusting invented receipt strings.

Only the assigned reviewer emits a `verification` event; the builder's final summary cites that review without impersonating its verdict. Count each actual send against the budget, including a separate root notification. Duplicate ingestion of the same call uses the original message ID and is recorded once. A new candidate event invalidates earlier verification, even if its hash is unchanged; a prose recap of an existing candidate is not a new candidate event.

## Independent review, direct repair, and recheck

1. Reviewer first assesses the contract and frozen artifact independently. Withhold builder conclusions and other reviewers' verdicts until that initial assessment is recorded. Earlier interface discussion is consultation, not independent verification.
2. Reviewer sends the active owner a finding with reproduction, expected/actual behavior, hash, and criterion ID. Owner acknowledges and edits only assigned files. Owner may challenge with evidence or send a repair candidate hash and test result. Agreement or a passing builder test alone does not resolve the finding.
3. Reviewer reopens the new bytes and tests the original counterexample plus a normal control. Record verification against that hash. Freeze the candidate while verifying; later edits invalidate verification.
4. For production acceptance, root binds the final verdict to a fresh counted reviewer attempt and final bytes. Earlier failed attempts remain in history with rejected acceptance. Keep one accepted final result per criterion; do not erase failures or accept unbound follow-ups.

Direct exchange makes repairs faster; it does not replace final independent acceptance.

## Disagreement and deadlock

Wait only until the acknowledgement deadline. Retry delivery once within budget, then escalate. Continue only independent work while waiting. Immediately escalate ownership collisions, incompatible contracts, missing authority, conflicting evidence, or absent peers. Otherwise use the allocated repair rounds, normally two. On exhaustion send root the disputed claim, each side's evidence, attempted repairs, and smallest remaining decision. Root serializes, revises the contract, reassigns within budget, defers a nonblocking issue, or stops that lane. Unresolved blocking issues prevent complete closure.

## Root-owned machine record

Runs using this protocol add `collaboration`:

- `mode: bounded_peer`, positive `message_budget`, `round_limit`;
- `peer_links`: directed `{from, to}` attempt-ID pairs; root links are implicit;
- `messages`: `{id, from, to, issue_id, type, round, revision, receipt}`;
- `issues`: `{id, owner, reviewer, state, blocking, revision}` and resolution fields below.

States: `open`, `acknowledged`, `proposed`, `verified`, `escalated`, `deferred`. Owner and reviewer are distinct known attempts. A verified issue needs `verified_revision == revision`, `resolution_receipt`, and a reviewer `verification` message with explicit `status: passed` after the owner candidate. A later finding, interface change, candidate, failed or blocked verification invalidates the old pass. A deferred issue must be nonblocking and carry `root_decision`. At complete closure all issues must be verified or explicitly deferred. Reassignment requires root to update IDs and preserve old attempts in history.

Checker validation establishes structural consistency, participants, limits, receipt presence, and closure rules only. Root additionally reopens actual message calls, acknowledgements, artifacts, and verification receipts. Confirm the ledger revision equals the real artifact SHA-256 at integration. Structure alone proves neither delivery nor reviewer independence.

If persisted message bodies are opaque or unavailable, retain call metadata and state that semantic replay was not possible. Use readable live acknowledgements and direct artifact verification where available; otherwise escalate the missing evidence. Do not decode protected payloads or fabricate a message transcript from a guessed exchange. Treat the lack of semantic replay separately from whether the final artifact independently passes its checks.

## Maintenance

Exercise a live isolated exchange: independent finding -> direct message -> acknowledgement -> repair -> recheck. Inject unavailable peers, exhausted budgets, stale hashes, unauthorized links, and unresolved blockers. Report which tests used live tools and which used synthetic records.
