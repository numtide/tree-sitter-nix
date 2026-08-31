# Oracles: tree-sitter-nix vs the Nix reference parser

Three cross-checks compare this grammar against `nix-instantiate --parse`
(the C++ Nix parser). All are stdlib Python 3 + POSIX sh, need
`nix-instantiate` and a tree-sitter CLI, and exit 0 only when nothing
regressed.

| Oracle       | Script                                      | Question it answers                                                             | Runtime |
| ------------ | ------------------------------------------- | ------------------------------------------------------------------------------- | ------- |
| precedence   | `operator_precedence_oracle.py`             | Do operators group and accept/reject like Nix? (347 synthetic cases + 15 files) | ~40 s   |
| differential | `differential.py`                           | Do both parsers agree on accept/reject for 1009 upstream test files?            | ~4 s    |
| shape        | `shape/compare.py` (uses `shape/ts2nix.py`) | Is the tree byte-for-byte equivalent to Nix's AST for 3000 nixpkgs files?       | ~10 s   |

Timings are with 32 jobs; the precedence oracle is serial (one
`nix-instantiate` per case).

## Environment variables

| Variable                          | Used by                     | Meaning                                                                                                                                                                                                                      |
| --------------------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TS_BIN`                          | all                         | tree-sitter CLI (default: `tree-sitter` on `PATH`).                                                                                                                                                                          |
| `TS_NIX_LIB`                      | differential, shape         | Prebuilt parser (`tree-sitter build -o nix.so`); needs a CLI with `parse --lib-path` (0.27 has it, 0.25.10 does not). Unset = the CLI runs from the repo root and compiles the grammar itself (what the Makefile and CI do). |
| `TREE_SITTER_LIBDIR`              | all (via the CLI)           | Where the CLI caches compiled parsers. Point it at a private dir when several jobs share a machine.                                                                                                                          |
| `NIX_BIN`                         | differential, shape         | `nix-instantiate` binary (default: on `PATH`).                                                                                                                                                                               |
| `NIXPKGS_PATH`                    | precedence                  | nixpkgs checkout for the 12 `lib/*.nix` corpus files (default: `<nixpkgs>`).                                                                                                                                                 |
| `NIXPKGS`                         | shape                       | Root that `shape/sample.txt` paths resolve against (fallbacks: `NIXPKGS_PATH`, then `<nixpkgs>`; `--root` overrides).                                                                                                        |
| `CORPORA_DIR`                     | fetch-corpora, differential | Where the pinned corpora live (default: `test/oracle/corpora`, gitignored).                                                                                                                                                  |
| `NIX_SRC`, `RNIX_SRC`, `SNIX_SRC` | fetch-corpora, differential | Existing checkouts of NixOS/nix, rnix-parser, snix. Skips the download for that corpus (fetch-corpora symlinks it; differential reads it).                                                                                   |

Every script prints its usage with `--help`.

## 1. Precedence oracle

```sh
TS_BIN=tree-sitter NIXPKGS_PATH=/path/to/nixpkgs \
  python3 test/oracle/operator_precedence_oracle.py .
```

For each `a OP1 b OP2 c` it asks both parsers whether the input is valid
and, when it is, which way it groups (by parenthesization equivalence on
the Nix side, by operand byte ranges on the tree-sitter side). Comparing
only accept/reject would pass with inverted precedence, which is what
slipped past PR #51. Also covers same-tier non-associative chains,
unary interactions, `!`-headed right operands, `?` chains, pipe
operators, and parses 12 operator-heavy nixpkgs `lib/*.nix` files plus
the repo's own `.nix` files.

When a grammar change touches operators, add the motivating cases to
`gen_extra_matrix()` before changing the grammar so the oracle locks in
the expected behaviour.

## 2. Differential oracle

```sh
sh test/oracle/fetch-corpora.sh          # once; idempotent
python3 test/oracle/differential.py --jobs "$(nproc)"
```

`corpora.lock` pins three upstream test suites (repo, commit, subdirs):
NixOS/nix `tests/functional/lang`, nix-community/rnix-parser
`test_data/parser`, snix `snix/eval/src/tests/{nix_tests,snix_tests}`
(snix is only on git.snix.dev; there is no GitHub mirror).
`fetch-corpora.sh` gets just those subdirs at those commits (blobless
sparse git fetch, falling back to a tarball of the commit via `gh api`
or the host's `/archive/` endpoint) into `$CORPORA_DIR/<name>/…` and
records the commit in `.corpus-rev`, so re-running is a no-op until the
lock changes. A `$CORPORA_DIR/<name>` that is a symlink is left alone,
which is how a sandboxed build pre-populates the corpora from its own
inputs. With local clones already on disk:

```sh
NIX_SRC=~/src/nix RNIX_SRC=~/src/rnix-parser SNIX_SRC=~/src/snix \
  python3 test/oracle/differential.py
```

Every file is run through `tree-sitter parse` (clean tree = accepted)
and `nix-instantiate --parse --extra-experimental-features
pipe-operators`. Nix rejections are classified from stderr: `syntax`
counts as rejected by the grammar; `undefined-variable`,
`semantic-bind` (duplicate attrs, dynamic attrs in `let`/`inherit`, …)
and `other` count as accepted, since a syntax-only parser cannot see
them. A file where the two verdicts differ is a disagreement. The full
per-file table goes to `test/oracle/out/differential.tsv`
(`--trees-dir DIR` also dumps every S-expression).

The run is compared against `baselines/differential-disagreements.tsv`
(file, corpus, ts_ok, nix_ok, nix_class — 16 rows today: trailing-slash
and `//` paths the grammar accepts, `or` used as an identifier, a bare
CR ending a comment, dynamic attrs in `let`/`inherit`). Any
disagreement not in the baseline, or one whose direction flipped, makes
the run exit with status 1; disagreements that vanished are printed as
improvements and the run exits 0.

## 3. Shape oracle

```sh
NIXPKGS=/path/to/nixpkgs \
  python3 test/oracle/shape/compare.py --jobs "$(nproc)" test/oracle/shape/sample.txt
```

`shape/ts2nix.py` walks the `tree-sitter parse -x` XML and re-prints it
exactly as `nix-instantiate --parse` prints its AST (the `show()`
functions of `nixexpr.cc`, the desugarings of `parser.y`: `a > b` →
`__lessThan b a`, `-a` → `__sub 0 a`, attrpath merging, indented-string
stripping, path canonicalisation, …). `compare.py` runs both on every
file of a list and diffs the bytes; a mismatch means the tree has the
wrong _shape_ even though it has no ERROR node. Statuses: `match`,
`mismatch`, `conv-error` (ERROR nodes or an unsupported construct),
`conv-exception` (converter bug), `nix-error` (Nix rejects the file, so
nothing to compare), `missing`. Exit 1 on mismatch / conv-error /
conv-exception. A few `missing` files only warn (nixpkgs revision
drift); more than 10% missing fails, since that means the root does not
hold the sampled trees; `--fail-on-missing` makes any missing file
fatal.
Results go to `test/oracle/out/shape.tsv` (`--out PREFIX`), and for
each mismatch both renderings are dumped under
`<PREFIX>.mismatches/<path>.{nix-parse,ts2nix}.txt`.

`shape/sample.txt` is a committed, deterministic sample of 3000 nixpkgs
paths (all 30 `lib/*.nix`, all 67 `pkgs/top-level/**`, 800 from
`nixos/modules/**`, 2103 from the rest of `pkgs/**`; seed 20260831,
sorted; drawn from nixpkgs b12141ef, the revision pinned in
`flake.lock`, which is what CI and the `oracle-shape` flake check run
it against). It must be regenerated whenever `flake.lock`'s nixpkgs
moves, or as soon as `compare.py` warns about missing files:
`NIXPKGS=$(nix eval --impure --raw --expr '(builtins.getFlake (toString ./.)).inputs.nixpkgs.outPath') python3 test/oracle/shape/make-sample.py`. Pass
an absolute path list (or `-` for stdin) to check anything else, e.g.
the whole of nixpkgs. A checkout used for the sample must hold the
sampled files: a sparse checkout can take them directly from the list
(`git sparse-checkout set --no-cone --stdin < <(grep -v '^#'
test/oracle/shape/sample.txt)`).

## How CI, the flake and the Makefile call them

The scripts are the single source of truth; every entry point runs the
same commands through the Makefile targets:

- `make oracle` — env `NIXPKGS_PATH=<nixpkgs checkout>`
- `make differential` — env `CORPORA_DIR`, or `NIX_SRC`/`RNIX_SRC`/`SNIX_SRC`
  for checkouts already on disk
- `make shape-oracle NIXPKGS=<nixpkgs checkout>` (or env `NIXPKGS_PATH`)

All three honour `TS=<tree-sitter cli>` (`TS_BIN` in the environment
overrides it), `JOBS=<n>` (default `nproc`) and `TREE_SITTER_LIBDIR`;
`TS_NIX_LIB` is never set by them.

In a Nix sandbox (flake checks) fetch the corpora at the commits in
`corpora.lock` and either symlink them into `$CORPORA_DIR/<name>`
(`fetch-corpora.sh` then leaves them alone) or point the overrides at
them:

```sh
export HOME=$TMPDIR TREE_SITTER_LIBDIR=$TMPDIR/ts-lib
NIX_SRC=${nix} RNIX_SRC=${rnix-parser} SNIX_SRC=${snix} \
  python3 test/oracle/differential.py --jobs "$NIX_BUILD_CORES"
NIXPKGS=${nixpkgs} python3 test/oracle/shape/compare.py --jobs "$NIX_BUILD_CORES" test/oracle/shape/sample.txt
```

`fetch-corpora.sh` needs network; plain `git` works on GitHub-hosted
runners for all three hosts. The tarball fallback uses `gh api` only
when `GH_TOKEN` is set (an unauthenticated `gh` falls through to
`curl`), and the Forgejo API archive endpoint for git.snix.dev. Cache
`test/oracle/corpora` keyed on `corpora.lock`.

## Updating baselines

- A grammar fix removes a disagreement: `differential.py` prints it as
  an improvement; run `python3 test/oracle/differential.py
--update-baseline` and commit `baselines/differential-disagreements.tsv`
  in the same change.
- A new disagreement is a bug unless it is a deliberate deviation from
  Nix; in that case add the row with `--update-baseline` and explain it
  in the commit message.
- Bumping a `*_REV` in `corpora.lock` can add upstream test files; run
  the differential oracle, triage every new row, then update the
  baseline.
- The shape oracle has no baseline: every sampled file must match. If a
  file legitimately cannot match (Nix rejects it), it shows up as
  `nix-error` and does not fail; drop it from `sample.txt` if it is
  noise.
- The precedence oracle has no baseline either; its expectations live
  in the case generators.
