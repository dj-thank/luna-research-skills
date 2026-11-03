# Check evidence at the question's time

Use this optional version 2 question with the [cross-source reader](cross-source-requirements.md)
when the answer depends on a declared validity interval. Root first fixes the
question's `as_of` timestamp and identifies the time-bearing answer and guard
requirements. Agreement between sources alone does not check whether their
agreed value applies at that time.

If the observation itself must also be recent, [version 3 adds a separate age
limit](observation-freshness.md). Validity alone does not check observation age.

Version 1 questions keep their existing output. Version 2 adds only explicit
time checks; it does not discover missing requirements, infer temporal meaning
from prose, retrieve fresher evidence or choose among conflicting facts.

## Declare the clock and windows

Retain the version 1 question fields, change `schema_version` to `2`, then add:

```json
{
  "as_of": "2031-06-15T12:00:00Z",
  "time_constraints": [
    {
      "id": "snapshot-window",
      "requirement": "snapshot",
      "valid_from": "/valid_from",
      "valid_until": "/valid_until"
    },
    {
      "id": "authority-window",
      "requirement": "authority",
      "valid_from": "/valid_from",
      "valid_until": "/valid_until"
    }
  ]
}
```

This is a fragment; the complete [question fixture](../tools/fixtures/temporal_question.json)
includes source pins and requirements. Each constraint has a unique simple ID,
references a declared requirement, and uses two distinct JSON Pointers into that
requirement's value. There must be 1–32 constraints. Only declared windows are
checked: root must identify every time condition needed for the receiving question.

Timestamps must be valid UTC calendar timestamps in exactly
`YYYY-MM-DDTHH:MM:SSZ` form, with years 0001–9999 and seconds 00–59. Numeric
timestamps, timezone offsets, fractional seconds, leap seconds and relative
expressions such as `now` are deliberately unsupported. Normalize with reviewed
semantics before pinning the input; this reader never guesses a conversion.

A declared interval is half-open: `valid_from <= as_of < valid_until`, and
`valid_from < valid_until`. End time equality is expired; start time equality
is valid. Neither a missing value nor null means an unbounded interval.
Validity is separate from observation time or maximum age: an old record can
correctly answer a historical question. This check never reads the host clock.

All sources, bindings and original observations are validated first. Existing
missing-source, unknown and conflict diagnostics take precedence. Only after
they are resolved does the reader check time. All matched observations of a
requirement already have identical typed values, so its window is checked once;
every observation and qualifier is still retained in a complete response.
Different source timestamps inside a value remain a conflict. Time does not
override the existing agreement rule or pick the newest record.

| Time diagnostic | Meaning |
| --- | --- |
| `MISSING` | A declared interval pointer cannot be resolved. |
| `UNKNOWN` | A selected endpoint is null. |
| `TIME_FORMAT` | An endpoint has an unsupported type, format or calendar value. |
| `INVALID_INTERVAL` | The start equals or follows the end. |
| `NOT_YET_VALID` | The question precedes the start. |
| `EXPIRED` | The question is at or after the end. |

A time gap returns `INSUFFICIENT` with `time_gaps` and no partial observations.
An invalid question, pin, binding or read/result budget returns `REFUSED`.
A complete result retains every value, qualifier and source origin, and adds
`as_of` and `time_checks` marked `COVERS_AS_OF`. The result envelope remains
schema version 1 with scope `declared_requirements_sources_and_time_only`.
Complete response limits include this metadata. Gap/refusal diagnostics are
separate from that limit, as in version 1.

## Run the pinned examples

Run from the repository or extracted plugin root with Python 3.11 or newer
(`py -3` on Windows, `python3` on macOS/Linux when needed). The future dates
and records are synthetic. The first example preserves an authority value of
`pending`; exit 0 means the declared checks matched, not approval.

```sh
python tools/read_requirement_sources.py --question tools/fixtures/temporal_question.json --sha256 b279cc7be10f3fb0a353c7cfcb935dedffd432fee97516c7697ef8f18bbc6e81 --source sender tools/fixtures/temporal_sender.json --source register tools/fixtures/temporal_register.json
```

The same sources at their end boundary return `INSUFFICIENT` / exit 1:

```sh
python tools/read_requirement_sources.py --question tools/fixtures/temporal_expired_question.json --sha256 2fa2b9a8999c7581a3622f17140555d8b07b378a51a74d5c6e8d6b30bea2a975 --source sender tools/fixtures/temporal_sender.json --source register tools/fixtures/temporal_register.json
```

## Bounded comparison

X31 froze 30 new cases before implementation: 8 complete views, 13 temporal
diagnostics, 3 inherited evidence gaps and 6 refusal controls. All matched the
fixed outcomes. The agreement-only baseline returned the timestamps but did not
diagnose the 13 temporal problems automatically. This is additional validation,
not proof that its receiver would have answered incorrectly or lost information.
The eight complete views retained exact records, typed values, qualifiers and
origins, including historical and negative facts. The previous 25 version 1
cases produced unchanged result objects and metrics after the reader changed.

For those eight complete views, source reads stayed at 16 / 10,636 bytes.
Question bytes increased from 4,392 to 6,520, with eight question reads in both
groups. Response bytes increased from 18,634 to 20,250 (+202 per view), within the
predeclared 1,024-byte increase limit. No speed, cost or model-quality benefit was
measured. Missing and unsupported timestamps deliberately fail closed.

[PAT-Questions](https://arxiv.org/abs/2402.11034v2), sections 1 and 3, motivates
distinguishing fixed-time questions from present-anchored questions and keeping
time-qualified answers. Our half-open interval contract is an engineering choice,
not the paper's SPARQL update method or a reproduction of its model benchmark.
This offline tool cannot verify that source windows are truthful, authoritative,
still accurate or semantically attached to the right fact. Root checks those
conditions and the completeness of the constraint set.

Frozen comparison SHA256:
`42d24014a04a0b0c01ab7909cc8432ddfc8cb3c9b1bac0174f960113f70bd28a`.

