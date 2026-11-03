# Bound observation age at the question's clock

A fact's declared [validity window](temporal-requirements.md) can cover the
question time even when the observation is too old for the receiving task.
Optional version 3 cross-source questions add a separate maximum observation-age
check. Root chooses which observations need a limit, what timestamp actually
records the observation, and the acceptable age before inspecting the outcome.

Version 3 retains the version 2 fields and requires `freshness_constraints`:

```json
{
  "freshness_constraints": [
    {
      "id": "snapshot-age",
      "requirement": "snapshot",
      "observed_at": "/observed_at",
      "max_age_seconds": 600
    },
    {
      "id": "authority-age",
      "requirement": "authority",
      "observed_at": "/observed_at",
      "max_age_seconds": 600
    }
  ]
}
```

This is a fragment; see the [complete pinned question](../tools/fixtures/freshness_question.json).
Each of 1–32 constraints has a unique ID within the freshness list, a declared
requirement, a JSON Pointer into that requirement's value, and an integer
`max_age_seconds` from 0 through 315537897599 (the full supported calendar span).
Boolean, float, string and negative limits are refused. IDs in the time and
freshness lists have separate namespaces and separate result fields.

The acceptance condition is `0 <= as_of - observed_at <= max_age_seconds`.
The maximum age is inclusive, and zero requires the same second. UTC whole
seconds are compared with exact integer arithmetic; the host clock is never
read. A historical question uses its explicit historical `as_of`, not today's
date. The same [strict UTC timestamp format](temporal-requirements.md#declare-the-clock-and-windows)
applies to the observation.

The reader selects only the declared pointer. It does not substitute receipt,
forwarding, file modification or validity-start times when the observation
timestamp is missing or stale. Root must verify that the pointer actually means
observation time: the tool cannot identify a mislabeled or fabricated timestamp.
Different timestamps within otherwise matching source values remain conflicts;
there is no newest-record selection or tolerance for clock skew.

All original records must first pass the existing subject, source coverage,
unknown and agreement checks. All declared validity windows must then pass.
Only after those gates does the reader check observation age. This preserves
earlier diagnostics and prevents freshness from overriding an expired fact.

| Freshness diagnostic | Meaning |
| --- | --- |
| `MISSING` | The declared observation pointer cannot be resolved. |
| `UNKNOWN` | Its value is null. |
| `TIME_FORMAT` | Its type, UTC format or calendar value is unsupported. |
| `FUTURE_OBSERVATION` | The observation follows the question time. |
| `STALE` | Its age exceeds the declared maximum. |

Any freshness gap returns `INSUFFICIENT` with `freshness_gaps` and no partial
observations or successful freshness checks. Invalid questions, pins, bindings
or budgets return `REFUSED`. A complete result adds `freshness_checks` with
`WITHIN_MAX_AGE`, `age_seconds` and `max_age_seconds`, retains all original
records, qualifiers and origins, and includes the time checks. The result
envelope remains schema version 1 with scope
`declared_requirements_sources_time_and_freshness_only`. Complete response
limits include all metadata; diagnostics retain the existing separate limit
behavior. Versions 1 and 2 keep their existing results.

Only declared requirements receive freshness checks. A recent timestamp does
not establish truth, permission, independence, current provider state or semantic
coverage. Validity and freshness are distinct policies, and passing them is
not approval. No network fetch, update scheduler or automatic threshold is added.

## Run the pinned examples

From the source or extracted plugin root with Python 3.11+ (`py -3` on Windows,
`python3` on macOS/Linux as needed), this synthetic example returns `OBSERVED`
/ exit 0. The observation age is 300 seconds against a 600-second maximum;
authority remains `pending`.

```sh
python tools/read_requirement_sources.py --question tools/fixtures/freshness_question.json --sha256 1c52fd7f26f891dc535d9174d7ac060efc21d7577c3543a74bb76d252802467b --source sender tools/fixtures/freshness_sender.json --source register tools/fixtures/freshness_register.json
```

The same records with a one-second snapshot limit return `INSUFFICIENT` / exit 1:

```sh
python tools/read_requirement_sources.py --question tools/fixtures/freshness_stale_question.json --sha256 d7ff50b040ed83e8a4752bb549899e67ce0b5b85258ba77163ca28f54e67c69c --source sender tools/fixtures/freshness_sender.json --source register tools/fixtures/freshness_register.json
```

## Bounded comparison

X32 fixed 32 new cases before implementation: 8 complete views, 10 observation-age
diagnostics, 4 inherited source/time gaps and 10 refusal controls. All matched
the expected outcomes. The interval-only baseline exposes observation times but
does not diagnose the ten age problems automatically. This adds deterministic
diagnostics; it does not demonstrate that a receiving agent would have missed
the same fact. Historical and negative facts retain their exact values,
qualifiers and origins. All 55 prior version 1/2 result objects and metrics
remained unchanged after this shared reader modification.

For the eight complete views, source reads stayed at 16 / 12,224 bytes.
Question reads stayed at eight, with bytes increasing 6,896 → 8,684.
Response bytes increased 21,748 → 23,820, within the predeclared extra 1,024-byte
limit per view. No speed, monetary cost or model-quality improvement was measured.

[Kaul, Yates and Gruteser (INFOCOM 2012)](https://www.winlab.rutgers.edu/~gruteser/papers/sanjitnew.pdf),
sections I and III, define update age from observer time and the update's
timestamp and distinguish timely information from delivery delay. Our fixed-clock
threshold is an engineering choice. This experiment does not reproduce their
queueing analysis, time-average metrics or update scheduling.

Frozen comparison SHA256:
`ef201a58456859e5970b5d0f81bbc94adaafb575aeb166a1c9f02be78f0a6113`.

