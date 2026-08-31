# test/bench — measurement loop

Every target below is wired into the top-level `Makefile` (`make help` lists
them). They re-measure the numbers from the grammar audit against a committed
baseline (`baseline.json`) so that a grammar change is judged by data, not by
eye. Everything is stdlib Python 3 + POSIX sh + C against `libtree-sitter`; no
paths are hardcoded.

## Prerequisites

| tool                                                   | used by                                              |
| ------------------------------------------------------ | ---------------------------------------------------- |
| tree-sitter CLI (`TS=`, default `tree-sitter` on PATH) | `test`, `bench`, `fuzz`, `oracle`, parser build      |
| tree-sitter CLI >= 0.27 (`parse --lib-path`)           | `bench` only (0.25.10 cannot time a prebuilt `.so`)  |
| a C compiler (`CC`)                                    | `memory`, `incremental`, `fuzz-asan`                 |
| `python3` (stdlib only)                                | all comparisons, `gen_patho.py`                      |
| a nixpkgs checkout (`NIXPKGS=`, default `../nixpkgs`)  | `bench`, `memory`, `incremental`, `shape-oracle`     |
| `nix-instantiate`                                      | `oracle`, `differential`, `shape-oracle`             |
| `curl` or `gh`                                         | only if libtree-sitter sources have to be downloaded |

### libtree-sitter for the C harnesses

`harness.c`, `rawwalk.c`, `incr_harness.c` and `asan_harness.c` link against
`libtree-sitter`. The Makefile resolves it in this order:

1. `TREE_SITTER_SRC=<checkout of tree-sitter/tree-sitter>`: compiles
   `lib/src/lib.c` once into `$(BUILD_DIR)/libtree-sitter.o`.
2. `pkg-config tree-sitter` if it reports version >= 0.25 (the first release
   that can load an ABI 15 parser). `rawwalk` is skipped in this mode: it
   needs the library's private headers (`lib/src/subtree.h`), so `memory`
   prints no hidden-node count.
3. Otherwise the release tarball matching `$(TS) --version` is downloaded into
   `$(BUILD_DIR)/tree-sitter-<version>/` with `curl`, falling back to
   `gh release download`.

The parser under test is always `$(BUILD_DIR)/nix.so`, built with
`$(TS) build -o`, i.e. exactly what a consumer of the CLI loads. Every CLI
invocation runs with `TREE_SITTER_LIBDIR=$(abspath $(BUILD_DIR)/ts-libdir)` so
concurrent checkouts never share the CLI's compiled-parser cache.

## Targets and variables

All variables can be given on the `make` command line or exported.

| target           | what it does                                                                                                                                                                                                                                                             | gate                                                                                          | variables                                                                                                                      |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `test`           | `tree-sitter test`, then compiles every `queries/*.scm` against `test/highlight/basic.nix` (`tree-sitter test` exits 0 on a broken query)                                                                                                                                | corpus 100 %, 6 queries compile                                                               | `TS`                                                                                                                           |
| `oracle`         | `test/oracle/operator_precedence_oracle.py .`                                                                                                                                                                                                                            | 0 failures                                                                                    | `TS_BIN` (default `$(TS)`), `NIXPKGS_PATH`                                                                                     |
| `differential`   | `test/oracle/fetch-corpora.sh` + `test/oracle/differential.py`                                                                                                                                                                                                           | disagreements <= committed baseline                                                           | `TS_BIN`, `CORPORA_DIR`, `NIX_SRC`/`RNIX_SRC`/`SNIX_SRC`                                                                       |
| `shape-oracle`   | `test/oracle/shape/compare.py test/oracle/shape/sample.txt`                                                                                                                                                                                                              | every file `match`                                                                            | `NIXPKGS`                                                                                                                      |
| `bench`          | `bench.sh`: `tree-sitter parse --stat`, then `interleave.py` runs HEAD's parser and `BASELINE_SO` alternately over `sample2000.txt`; `compare_bench.py` gates                                                                                                            | median <= reference x `BENCH_THRESHOLD`, 0 failed parses                                      | `NIXPKGS`, `BENCH_RUNS` (10, min 5), `BENCH_WARMUP` (2), `BENCH_THRESHOLD` (1.10), `BASELINE` (`baseline.json`), `BASELINE_SO` |
| `memory`         | `memory.sh`: `mem_harness stats` (counting allocator -> tree bytes, node counts), `mem_harness reuse` (RSS, leak check), `rawwalk` (hidden nodes), then `compare_memory.py`                                                                                              | bytes/node <= baseline x `THRESHOLD`, no ERROR/MISSING, 0 bytes live after `ts_parser_delete` | `NIXPKGS`, `MEMORY_LIST` (`sample2000.txt`; `full` = every `.nix` under `NIXPKGS`), `THRESHOLD`, `BASELINE`                    |
| `incremental`    | `incr_harness`: for each file of `incremental-sample.txt` and each of `INCR_NPOS` positions, 18 edits (insert/delete/replace one char, insert each Nix delimiter, delete 2 bytes); the incremental reparse must equal a fresh parse                                      | mismatches <= `INCR_MAX`                                                                      | `NIXPKGS`, `INCR_NPOS` (10), `INCR_MAX` (0)                                                                                    |
| `fuzz`           | `tree-sitter fuzz` with a fixed seed; the CLI exits 0 on failure so its output is grepped                                                                                                                                                                                | no `Incorrect` parse                                                                          | `FUZZ_SEED` (20260831), `FUZZ_EDITS` (10), `FUZZ_ITERATIONS` (300)                                                             |
| `fuzz-asan`      | `gen_patho.py` writes pathological inputs + one file per corpus example into `$(BUILD_DIR)/patho/`; `asan_harness` (parser.c + scanner.c, and lib.c when built from source, with `-fsanitize=address,undefined -fno-sanitize-recover=all`) parses them and `patho/*.nix` | no sanitizer report, every parse returns a tree                                               | `PATHO_PROFILE` (`ci` or `full`), `PATHO_QUADRATIC` (1 adds `patho/quadratic/`), `SAN_FLAGS`                                   |
| `bench-baseline` | rewrites `BASELINE` from the last `bench`, `memory` and `incremental` results                                                                                                                                                                                            | –                                                                                             | `BASELINE`, `RESULTS_DIR`                                                                                                      |

Common: `BUILD_DIR` (`build`), `RESULTS_DIR` (`test/bench/results`, gitignored),
`TREE_SITTER_SRC` (see above). `THRESHOLD` (1.05) gates the deterministic
bytes/node number; wall-clock gets the wider `BENCH_THRESHOLD` (1.10). With
`fuzz-asan`, lib.c is only instrumented when it is compiled from
`TREE_SITTER_SRC` or the downloaded tarball; with pkg-config the system
`libtree-sitter` is linked as is and only parser.c and scanner.c are
sanitized. Wall-clock per target on a 32-core Xeon 8488C:
`test` 3 s, `bench` 10 s, `memory` 2 s, `incremental` ~3.5 min (54 000 edits,
108 000 parses), `fuzz` 3 s, `fuzz-asan` ~55 s.

## Data files

- `sample2000.txt` — 2000 nixpkgs files, paths relative to `NIXPKGS`. This is
  the audit's `sample2000` (fixed-seed sample of `nixpkgs-files.txt`), so the
  numbers are directly comparable with the audit report.
- `incremental-sample.txt` — 300 nixpkgs files (the audit's `files-300`),
  relative paths.
- Both lists exist only at one nixpkgs revision, recorded as `nixpkgs_rev` in
  `baseline.json` (`bench-baseline` takes it from `NIXPKGS_REV` or
  `git -C $(NIXPKGS) rev-parse HEAD`); `bench.sh` and `memory.sh` fail on any
  missing file rather than measure a smaller set, and `nightly.yml` checks
  nixpkgs out at that revision. Move the lists and the baseline together.
- `patho/*.nix` — hand-written and minimised reproducers from the audit's
  fuzzing (scanner edge cases, NUL bytes, BOM, path/URI shapes, mutants).
  Always parsed by `fuzz-asan`.
- `patho/quadratic/*.nix` — the R1-010 / R1-019 inputs that take seconds to
  tens of seconds with the current grammar (`a + + /**/ + + …`, 32k-operator
  chains). Parsed only with `PATHO_QUADRATIC=1`; they become part of the
  default set once the grammar fix lands.
- `baseline.json` — reference numbers; see below.

## baseline.json

```json
{
  "commit": "…", "date": "…", "machine": {"cpu": "…", "cores": 32, "os": "…"},
  "tree_sitter_cli": "0.27.0", "nixpkgs_rev": "…",
  "bench":   {"median_ms": …, "mean_ms": …, "stddev_ms": …, "runs": …, "bytes_per_ms": …, "failed_parses": 0},
  "memory":  {"bytes_per_node": …, "hidden_internal": …, "peak_rss_kb": …, "nodes": …, …},
  "incremental": {"files": 300, "npos": 10, "edits": 54000, "mismatches": …},
  "state_count": …, "symbol_count": …, "token_count": …, "language_version": 15
}
```

What is compared:

- `bench`: `median_ms` (median wall-clock of `tree-sitter parse -q --paths`
  over the sample, `BENCH_RUNS` runs after `BENCH_WARMUP` warm-ups; mean,
  stddev, min and max are recorded too). Ratio candidate/reference must be <=
  `BENCH_THRESHOLD`. **This number is machine-specific and load-sensitive**: on
  the baseline host it moved from 479 ms (idle) to 759 ms (load average 19)
  within a minute, and two runs of the _same_ binary measured back to back
  differed by 45 % under changing load. Two ways to get a fair comparison:
  - `make bench BASELINE_SO=/path/to/reference-nix.so` — `interleave.py` runs
    the two parsers alternately (A B A B …, order flipped every round) so load
    changes hit both, and `compare_bench.py` compares the medians; this is what
    the nightly does (build the reference from the baseline commit with
    `tree-sitter build -o`). hyperfine is not used because it runs all of A,
    then all of B.
  - refresh the baseline on the same runner class with `make bench-baseline`.
- `memory`: `bytes_per_node` (tree bytes as seen by a counting allocator
  installed with `ts_set_allocator`, divided by visible nodes). This is
  deterministic for a given parser + libtree-sitter version and is the metric
  the hidden-rule layering of the grammar moves (audit: 159.5 B/node fork vs
  100.8 upstream). `hidden_internal` (from `rawwalk`) and `peak_rss_kb` are
  printed for context, not gated.
- `incremental.mismatches` is recorded for reference only; the target's gate
  is `INCR_MAX` (default 0).
- `state_count` etc. are recorded so a grammar PR can show the table-size delta.

### Updating the baseline

Only after a deliberate grammar/scanner change whose effect on the numbers has
been reviewed, and on a quiet machine:

```sh
make bench BENCH_RUNS=20   # check the stddev is a few ms, not tens
make memory
make incremental INCR_MAX=999   # or whatever the current mismatch count is
make bench-baseline        # rewrites test/bench/baseline.json, prints it
git diff test/bench/baseline.json   # review, then commit with the grammar change
```

`bench-baseline` records the commit, date, CPU model, core count, OS and CLI
version alongside the numbers.

## Current state (recorded in baseline.json at commit 70f34e9)

- sample2000 (nixpkgs 597647d3): 479.3 ± 3.1 ms mean over 20 hyperfine runs
  on an idle host, recorded as both `mean_ms` and `median_ms` (the per-run
  times of that session were not kept); `--stat` 10 955 bytes/ms; 2000/2000
  parse.
- memory (sample2000): 157.85 B/node, 830 919 visible nodes, 1 046 577 hidden
  internal nodes (rawwalk), peak RSS 13 MB, 0 bytes live after
  `ts_parser_delete`.
- incremental: 1 mismatch in 54 000 edits (R2-009: inserting `/` right after a
  line comment that precedes `++` in `pkgs/by-name/gi/gitbutler/package.nix`).
  Until the grammar fix lands, run `make incremental INCR_MAX=1`.
- fuzz: 83 corpus tests x 300 iterations x 10 edits, seed 20260831: clean.
- fuzz-asan (`ci` profile): 140 pathological + 84 corpus + 31 reproducer
  files, no sanitizer report; slowest parse 4.4 s (1 MB `"${a}${a}…"` string)
  under ASan.
- STATE_COUNT 635, SYMBOL_COUNT 122, TOKEN_COUNT 67.

## Files

| file                | role                                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `bench.sh`          | bench driver (`RUNS`, `WARMUP`, `NIXPKGS`, `TS`, `RESULTS`, `SAMPLE`)                                                     |
| `interleave.py`     | times commands alternately, writes hyperfine-layout JSON (used by `bench.sh`)                                             |
| `compare_bench.py`  | gate for `bench`; `--write-baseline` implements `bench-baseline`                                                          |
| `memory.sh`         | runs `mem_harness stats`/`reuse` and `rawwalk` (`LIST`, `RAWWALK`, `NIXPKGS`, `RESULTS`)                                  |
| `compare_memory.py` | folds the memory outputs into `results/memory.json` and gates bytes/node                                                  |
| `harness.c`         | memory/tree-shape harness (`stats`, `reuse` modes)                                                                        |
| `rawwalk.c`         | raw `Subtree` walk: inline/heap/hidden node counts (needs private headers)                                                |
| `incr_harness.c`    | incremental-vs-fresh differential; mismatches dumped to `results/incremental/mismatch-N.{incr.txt,full.txt,new.nix,meta}` |
| `asan_harness.c`    | sanitizer parse harness, iterative tree walk (50k-deep inputs)                                                            |
| `gen_patho.py`      | generates pathological inputs (`--profile ci`/`full`) and splits `test/corpus`                                            |
