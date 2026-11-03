# Prepare exact source bytes from a pinned Git commit

Checkout filters and newline settings can change bytes before a probe runs. A local package replay exposed this: the patch applied, but its raw source bytes differed and the exact-diff gate stopped. Rewriting every CRLF to LF is also unsafe when data deliberately contains CRLF or bare CR.

Use the source-only `tools/prepare_source_snapshot.py` for a **reviewed subset of files from a trusted local repository**. It reads raw Git blobs, checks an independently pinned manifest, and writes a new directory only with `--apply`. It does not check out a branch, apply a patch, execute the source, install dependencies, or change Git configuration.

## Specify the expected scope

A manifest has exactly these fields:

```json
{
  "schema_version": 1,
  "commit": "FULL_40_CHARACTER_SHA1_COMMIT_ID",
  "files": [
    {
      "path": "src/task.py",
      "mode": "100644",
      "bytes": 11,
      "sha256": "INDEPENDENTLY_REVIEWED_SHA256_OF_THE_RAW_BLOB"
    }
  ]
}
```

Review the commit and expected bytes independently. Do not generate acceptance pins from the output being judged. The helper supports Git regular-file modes 100644/100755, at most 64 files, 1 MiB per file and 8 MiB total. Paths are a conservative ASCII subset, with case collisions, Windows device names, parent traversal, file/directory overlaps and `.git` components rejected. SHA256-format Git repositories, symlinks and submodules are outside this version's contract.

From the source repository/archive, with Python 3.11+ and Git supporting `--no-lazy-fetch`:

```sh
python tools/prepare_source_snapshot.py --repo PATH_TO_REPOSITORY_ROOT --manifest reviewed.json --sha256 REVIEWED_MANIFEST_SHA256 --target NEW_DIRECTORY
python tools/prepare_source_snapshot.py --repo PATH_TO_REPOSITORY_ROOT --manifest reviewed.json --sha256 REVIEWED_MANIFEST_SHA256 --target NEW_DIRECTORY --apply
```

The parent must already exist and be a direct directory. The target must not exist, even as an empty directory, and cannot overlap the source checkout or its Git metadata. Static symlink/reparse ancestors are rejected; the existing installer's documented macOS system aliases are allowed.

The default returns `PLAN` with no target writes. Apply preloads and verifies **all** selected blobs, creates the target exclusively, writes the exact bytes, then reads them back before returning `EXPORTED`. Both exit 0. A preflight failure returns `REFUSED` and exits 2. An I/O failure after creation returns `INCOMPLETE`, also exits 2, and preserves the partial directory for inspection. Never consume it as an accepted snapshot or retry over it. No existing files or failed outputs are deleted.

The manifest pins content, size and Git mode. POSIX executable bits are set on new files; Windows ACL/permission equivalence is not claimed. The file list is an explicit subset, not proof that every runtime dependency has been captured.

## Comparison and failure tests

Run the fixed comparison from the source package:

```sh
python tools/example_canonical_source.py --work NEW_EXPERIMENT_DIRECTORY
python -m unittest discover -s tools -p test_prepare_source_snapshot.py
```

Omit `--work` to use a temporary fixture directory. The comparison creates its own tiny Git histories; it never reruns the external more-itertools task. Literal expected bytes and decisions were fixed before candidate implementation in `tools/fixtures/canonical_source_oracle.json`.

Three profiles use LF, `core.autocrlf=true`, and `core.eol=crlf`. Each has an accepted code change and a numeric-constant mutation that must be rejected. The fixture includes binary data containing CRLF, bare CR and a non-UTF8 byte, which must remain exact.

| Preparation policy | Valid cases retained | Mutations rejected | Correct decisions |
|---|---:|---:|---:|
| Checkout and apply with the selected profile | 1/3 | 3/3 | 4/6 |
| Raw blobs checked against reviewed pins | 3/3 | 3/3 | 6/6 |
| Blanket newline replacement after apply | 0/3 | 3/3 | 3/6 |

The raw-blob helper avoided the two false rejections while preserving all three mutation rejections. The blanket replacement corrupted legitimate data and is not adopted. All policies had zero false acceptance in these six cases. These are preparation results, not speed, cost or reasoning measurements.

The tests also cover a same-size code mutation, independent-pin and duplicate-JSON rejection, byte/file budgets, existing destinations, source/metadata overlap, symlink/gitlink entries, replacement refs, ambient Git environment overrides, executable modes, CLI dry-run/apply, and an injected write failure. They use local Git fixtures on CI's Windows/macOS/Linux matrix; no provider or historical package execution is required.

The original comparison and failed X41 replay remain preserved in the local work records. Root review added explicit system-attribute isolation to the Git subprocess environment; the revised candidate reproduced the same six results with the oracle unchanged. Existing readers and installed skills remain unchanged.

## Basis and boundaries

[Git cat-file](https://git-scm.com/docs/git-cat-file) distinguishes raw blob contents from optional working-tree filters. [Git attributes](https://git-scm.com/docs/gitattributes) explains checkout newline conversions and `-text` preservation. This helper uses raw object reads with replacement objects and lazy fetching disabled, and ignores ambient Git override variables. It does not normalize blob contents.

[Le, Afshari and Su, PLDI 2014](https://www.vuminhle.com/pdf/pldi14-emi.pdf), abstract/introduction pp. 1–2, motivates testing controlled variants against a relation on fixed inputs. Here the variants are preparation configurations and the oracle is exact bytes. This is not a replication of their compiler experiment or a general equivalence proof.

Use stable, single-writer paths and trusted local Git repositories. The helper is not a concurrent-filesystem sandbox, source-authenticity service, crash-atomic publisher or whole-environment capture. A pin establishes selected identity, not correctness of the chosen source. Root performed the bounded review; native delegation remained 6/6 with no new blind or independent agent.
