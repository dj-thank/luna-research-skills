# Contributing

Keep the model guarantee fail-closed and evidence-based. A change to routing behavior should include both a positive runtime-metadata test and a negative test that rejects a different model.

Before opening a pull request, run:

```bash
python -m compileall -q plugins
python -m unittest discover -s tests -v
```

Keep each Skill's `SKILL.md` under 500 lines, place branch-specific detail behind a direct reference, and preserve read-only planning before configuration writes.
