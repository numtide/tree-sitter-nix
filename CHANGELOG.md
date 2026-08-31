# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `workflow_dispatch` input `tag` on `publish.yml` to dry-run the whole
  release pipeline against an existing tag
  (`gh workflow run publish.yml -f tag=v0.5.0`): checks out the tag,
  builds every asset, and reports what the tag's release is missing as
  warnings. Nothing is uploaded, attested, or published on dispatch.
  (R1-033, R2-026)
- `verify-release` job at the end of `publish.yml`: re-downloads the
  release assets, checks that all four (`.wasm`, `.wasm.sha256`,
  `.tar.gz`, `.tar.gz.sha256`) are present, runs
  `sha256sum -c --strict`, compares the released `.wasm` byte-for-byte
  with the one the run built, runs `gh attestation verify` on both
  artifacts, and polls crates.io for the crate version. Fatal on tag
  push, warnings on dispatch. (R1-033, R2-026)
- Measurement harness under `test/bench/` wired into the Makefile, so
  the numbers the audit measured by hand can be re-measured with one
  command each: `make bench` (`tree-sitter parse` over
  `test/bench/sample2000.txt`, run alternately with a reference parser
  (`BASELINE_SO`) so machine load hits both, gated on the ratio of
  medians (`BENCH_THRESHOLD`) against `test/bench/baseline.json`,
  written by `make bench-baseline`; needs CLI >= 0.27 for
  `parse --lib-path`), `make memory` (bytes per node, hidden
  nodes, RSS; `THRESHOLD`), `make incremental` (an incremental reparse must equal a
  fresh parse over `test/bench/incremental-sample.txt`, `INCR_MAX`),
  `make fuzz` (fixed seed), `make fuzz-asan` (ASan/UBSan over the
  corpus plus the pathological inputs from `test/bench/gen_patho.py`)
  and `make bench-baseline`. Every `tree-sitter` invocation from
  `make` now runs with a private `TREE_SITTER_LIBDIR` under `build/`,
  so concurrent jobs no longer share the CLI's compiled-parser cache
  (R2-036). `make test` also compiles all six `queries/*.scm` files.
- Oracles under `test/oracle/`: `differential.py` (accept/reject of
  every file in the nix, rnix-parser and snix test corpora against
  `nix-instantiate --parse`, with the 16 known disagreements committed
  as `baselines/differential-disagreements.tsv`), `shape/compare.py`
  (`ts2nix.py` prints the tree-sitter AST back as Nix and
  `nix-instantiate --parse` must yield the same normal form, over a
  3000-path nixpkgs sample in `shape/sample.txt`), and
  `fetch-corpora.sh` with the corpus revisions pinned in
  `corpora.lock`. Exposed as `make oracle`, `make differential`,
  `make shape-oracle` and as the flake checks `oracle-precedence`,
  `oracle-differential`, `oracle-shape`.
- `tree-sitter-cli` 0.25.10 as a `devDependency` (and a `files` list)
  in `package.json`, so `npm ci && npx tree-sitter` gives the
  generator that produced `src/parser.c` on a clean machine; the
  `generator-version` flake check fails when the flake's tree-sitter
  drifts from the `@generated` header. (R1-011, R2-029)
- `.github/workflows/ci.yml`: the repo had no CI on pull requests. The
  new workflow runs on every PR and on `master`: generated sources
  must match what the pinned CLI emits (`tree-sitter generate --abi 15`
  then `git diff --exit-code -- src/`), corpus tests and a fixed-seed
  fuzz, every `queries/*.scm` compiles, the three oracles against
  `nix-instantiate` and the reference corpora (cached by the hash of
  `test/oracle/corpora.lock`), `nix flake check --no-build`, and one
  job per binding (rust, python, go strict; node and zig
  `continue-on-error` until R1-004/R1-063 are fixed). Each job runs
  the CLI with a private `TREE_SITTER_LIBDIR` (R2-036).
- `.github/workflows/nightly.yml`: the non-blocking measurement loop
  from the audit, on a daily cron and on demand. It parses all of
  nixpkgs with a gate of zero failed parses and counts `MISSING` nodes
  on a fixed sample (R1-049), benchmarks HEAD against a parser built
  from the baseline's commit (CLI `tree_sitter_cli` from
  `baseline.json`, 0.27.0), and runs the `memory`, `incremental` and
  `fuzz-asan` harness targets against a libtree-sitter built from the
  generator's own tree-sitter tag. The sample lists are only valid at
  the nixpkgs revision recorded as `nixpkgs_rev` in `baseline.json`,
  which is the one these jobs check out (the PR oracles follow
  `flake.lock`; `test/oracle/shape/sample.txt` is drawn from that
  pin). Results are uploaded as workflow artifacts; nothing in it
  gates a PR.
- `flake.nix`: the generator version is read from the `@generated`
  header of `src/parser.c` instead of being hard-coded, a
  `generator-version` check fails when nixpkgs' `tree-sitter` moves
  away from it, the version of record is `package.json` (R1-032), and
  the reference corpora for the oracle checks are fetched at the
  revisions in `test/oracle/corpora.lock`.
- SLSA build provenance attestations for release artifacts. The
  `release-wasm` and `release-tarball` jobs now generate a
  cryptographically signed attestation tying each artifact's digest
  to the workflow run, repo, ref, and commit SHA. Verifiable
  downstream with `gh attestation verify <file>` plus a `--repo`
  flag. Recorded in the public Sigstore transparency log. The crate
  published to crates.io is not attested here — crates.io has its
  own provenance roadmap and `cargo publish` doesn't emit a local
  artifact to attest. Documented in the README under "Release
  artifacts and provenance". [#57]
- Source tarball attached to GitHub releases. `publish.yml` now has a
  `release-tarball` job that builds `tree-sitter-nix.tar.gz` from
  `git ls-files` plus the generated parser sources. The tar
  invocation pins owner, group, mode, sort order (`LC_ALL=C`), and
  mtime so the SHA256 is stable for a given commit. Unlike GitHub's
  auto-generated `/archive/...` tarballs, the uploaded asset never
  changes — safe for `fetchurl` consumers in nixpkgs / Bazel / Buck.
  File selection mirrors tree-sitter's official `release.yml`
  reusable workflow. [#56]
- WASM build attached to GitHub releases. `publish.yml` now has a
  `release-wasm` job that builds `tree-sitter-nix.wasm` (with
  emscripten 4.0.4, matching tree-sitter 0.25.10's pin), validates
  the module structure with `WebAssembly.Module()` (full validation,
  not just the magic header) and checks for a `tree_sitter_*` export,
  generates a SHA256 checksum, and uploads both to the existing
  GitHub release on tag push via `gh release upload`. Closes [#14].
  [#55]

### Changed

- `cargo publish` in `publish.yml` is idempotent: the job reads the
  crate name and version from `Cargo.toml` via `cargo metadata` and
  skips the publish when crates.io already serves that version, so a
  re-run after a partially failed release is green instead of red.
- The WASM toolchain is a single pinned pair,
  `TREE_SITTER_CLI_VERSION` (0.25.10) and `EMSCRIPTEN_VERSION` (4.0.4),
  asserted in three places before anything is built: the `@generated`
  header of `src/parser.c` must name that CLI, the installed
  `tree-sitter --version` and `emcc --version` must match, and
  tree-sitter's own `cli/loader/emscripten-version` at that tag must
  equal the emsdk pin. CLI ≥ 0.26 ignores emsdk and downloads an
  unpinned wasi-sdk, so a silent bump can no longer change the blob.
  (R2-030)
- `tree-sitter-nix.wasm.sha256` records the exact `tree-sitter-cli`
  and emscripten versions in `#` comment lines (accepted by
  `sha256sum -c --strict`); the tarball sidecar records the source
  commit. The digest of a tree-sitter WASM build depends on the CLI
  version, so the note tells consumers which CLI to rebuild with for
  a matching hash. The README release section documents the assets,
  how to verify them, and the CLI caveat. (R2-034)

### Fixed

- Tag-push releases publish to crates.io again. `publish.yml`
  referenced a secret `CARGO_REGISTRY_TOKEN` that does not exist; the
  numtide org secret is `CRATES_IO_TOKEN` (visible to this repo via
  the organization-secrets API). A preflight step now fails with a
  clear message when the token is empty instead of a bare "please
  provide a non-empty token" from `cargo publish`. (R1-003)
- Release assets no longer depend on a human creating the GitHub
  release before the tag-push run reaches `gh release upload`. The
  `verify` job creates a draft release (`--generate-notes`,
  `--verify-tag`) when none exists, exactly once, before the upload
  jobs run; they upload into it and a maintainer publishes the draft.
  v0.4.0/v0.5.0 predate the asset jobs; the only tag-push runs so far
  failed in the crates.io publish step (R1-003). (R1-033, R2-026)
- Node 20 actions in `publish.yml` retired by GitHub on 2026-09-16/23
  replaced with their Node 24 majors, SHA-pinned and checked for
  `runs.using: node24` at the pinned tag: `actions/setup-node` v4.4.0
  → v7.0.0, `actions/upload-artifact` v4.4.3 → v7.0.1,
  `mymindstorm/setup-emsdk` v14 → v16 (also fixes the "Cache service
  responded with 400" from its retired `@actions/cache` backend),
  `actions/attest-build-provenance` v3.2.0 → v4.2.2 (composite over
  `actions/attest` node24), plus `actions/download-artifact` v8.0.1
  for the new job. (R1-036)
- `bindings/go` compiles from a clean clone again: `go.mod` bumped
  `github.com/tree-sitter/go-tree-sitter` v0.24.0 → v0.25.0 (the
  first release that loads an ABI 15 parser) and `go.sum` is committed
  next to it. (R1-013)
- `src/scanner.c` includes `"tree_sitter/parser.h"` with quotes
  instead of angle brackets, so the header next to it is found
  without an extra `-I` flag, the way the generated `parser.c` does
  it. `CMakeLists.txt` project version 0.3.0 → 0.5.0, matching
  `Cargo.toml`.
- Equality (`==`, `!=`) and comparison (`<`, `<=`, `>`, `>=`) are now
  non-associative, matching Nix's `%nonassoc` declarations. Chained
  expressions like `1 == 2 == 3` and `1 < 2 < 3` are now parse errors,
  exactly as in Nix. Cross-tier mixing like `1 == 2 < 3` and
  parenthesized chains like `(1 == 2) == 3` continue to parse.
  Implemented with a hybrid grammar: only the two non-associative
  tiers are separate structural rules (so a chain cannot be derived),
  while every associative operator stays in a flat `prec`-annotated
  rule — the same fast encoding used before #52. Validated against
  `nix-instantiate` on a 341-case cross-check matrix (committed at
  `test/oracle/`) that compares both accept/reject AND parse-tree
  grouping. The public `binary_expression`, `unary_expression`, and
  `has_attr_expression` node types — and the entire `node-types.json`
  — are byte-identical to the previous flat grammar. Closes [#52].
  [#58], [#59]

## [0.5.0] — 2026-05-18

### Added

- Filename-based language injection for indented strings. Curried calls
  like `pkgs.writeText "page.html" '' … ''` now inject the language
  matching the filename extension. 14 extension classes are supported:
  `.sh`/`.bash`, `.py`, `.html`/`.htm`, `.css`, `.js`/`.mjs`/`.cjs`,
  `.ts`/`.mts`/`.cts`, `.json`, `.yml`/`.yaml`, `.toml`, `.lua`,
  `.nix`, `.xml`, `.md`, `.sql`. A function denylist (`removeSuffix`,
  `trace`, `throw`, etc.) excludes common nixpkgs idioms that take a
  filename-shaped string but aren't file writers. Replaces the two
  `writeText*`-only patterns shipped in v0.4.0. Concept harvested from
  nix-community/tree-sitter-nix#169 by @nuketownada. [#53]
- `queries/folds.scm` — fold ranges matching nvim-treesitter's vendored
  Nix fold set (attrsets, lists, indented strings, let/with/if
  expressions, function bodies), plus `let_attrset_expression`,
  `block_comment`, and `doc_comment`. Also exposed as
  `tree_sitter_nix.FOLDS_QUERY` in the Python binding. [#49]
- OCaml bindings under `bindings/ocaml/` — hand-written dune package
  with a self-contained libtree-sitter runtime wrapper (`Parser`,
  `Tree`, `Node` modules). No dependency on ocaml-tree-sitter-core.
  [#40]

### Fixed

- Home paths with leading interpolation (`~/${x}`, `~/${x}/config`)
  now parse. The previous `_hpath_start` regex required at least one
  path char after `~/`, so it could not stop before `${`. The new
  rule mirrors Nix's lexer.l, which has a separate `HPATH_START`
  production for exactly this case. [#50]

### Changed (BREAKING for theme consumers)

- `highlights.scm` capture names modernized to align with
  [nvim-treesitter conventions](https://neovim.io/doc/user/treesitter.html#treesitter-highlight-groups).
  Themes that string-map the old capture names will need to add
  fallbacks; modern tree-sitter theme distributions (Tokyo Night,
  Catppuccin, Gruvbox-Material, etc.) already support the new names.
  Full rename table in
  [docs/highlight-groups.md](docs/highlight-groups.md#renames-from-v04x-and-earlier).
  Notable renames: `@escape` → `@string.escape`,
  `@string.special.uri` → `@string.special.url`,
  `@property` → `@variable.member`, `@keyword` split into
  `@keyword.conditional` / `@keyword.operator` / `@keyword`,
  booleans → `@boolean`, constants → `@constant.builtin`,
  apply-position function → `@function.call`. Added `@spell` on
  comments, `@keyword.import`, `@keyword.exception`,
  `@variable.parameter.builtin` for `...`. [#48]

## [0.4.0] — 2026-05-11

### Added

- Comment subtypes: `comment` is now a supertype covering `line_comment`
  (`# …`), `block_comment` (`/* … */`), and `doc_comment` (`/** … */`,
  RFC 145 / nixdoc). Existing queries targeting `(comment)` continue to
  match all three via the supertype; consumers that compare node-type
  strings will see the concrete type. Regex shapes lifted from Nix's own
  flex lexer so edge cases (`/**/`, `/***/`) classify identically. Also
  adds `(doc_comment) @comment.documentation` in `highlights.scm`. [#45]
- Zig bindings (`bindings/zig/`, `build.zig`, `build.zig.zon`) via
  `tree-sitter init` with `zig: true` in `tree-sitter.json`. [#39]
- C, Go, Python, Swift bindings materialized under `bindings/`; previously
  only declared in `tree-sitter.json` but missing on disk. [#38]
- `queries/indents.scm` covering attrsets, lists, let/in, if/then/else,
  function formals, and interpolation alignment. [#36]
- Expanded `queries/injections.scm` — `lib.literalExpression` (nix),
  `testScript` (python), `writeShellApplication` with let-bound text,
  `writeText*` by filename extension (bash/python), and comment-prefix
  normalization so `# bash` / `#bash` / `/* bash */` all resolve to
  `bash`. [#36]
- Expanded `queries/tags.scm` — generic `@definition` / `@reference`
  captures, `inherit` / `inherit_from` definitions, method-style
  `@reference.call`. GitHub code-nav now produces meaningful tag hits.
  [#36]
- Pipe operators `|>` (left-assoc) and `<|` (right-assoc) from Nix 2.24+.
  Harvested from upstream nix-community/tree-sitter-nix#159 by
  @mightyiam. [#33]
- Empty `inherit (expr);` is now accepted (symmetric with empty
  `inherit;`). [#34]
- `__curPos`, `__addDrvOutputDependencies`, `__convertHash`, `__warn`
  added to `highlights.scm` builtins. [#35]
- TypeScript declarations (`bindings/node/index.d.ts`) and Node smoke
  test (`bindings/node/binding_test.js`). [#38]

### Changed

- Rust edition bumped from 2018 to 2024; `extern "C"` → `unsafe extern "C"`.
  [#41]
- Mergify auto-merge rule references `all-checks-passed` (was `collect`).
  [#41]
- Publish workflow modernized — `dtolnay/rust-toolchain` replaces
  archived `actions-rs/toolchain`, `Swatinem/rust-cache` replaces manual
  `actions/cache`, `--locked` added to `cargo publish`, tag-vs-manifest
  guard, split into `verify` + `release` jobs. [#26]
- Nix flake workflow tightened — `permissions: contents: read`,
  concurrency group, fork-resilient `cachix-action`, dropped `main`
  branch trigger, renamed `collect` → `all-checks-passed`. [#27]
- All third-party actions pinned to commit SHAs. [#29]
- CI Linux runners moved from Namespace Cloud (`nscloud-*`) to GitHub-
  hosted (`ubuntu-latest`, `ubuntu-24.04-arm`); macOS updated to
  `macos-15-intel`. [#28, #1]
- `tree-sitter` dev-dep bumped `>=0.25.0` → `>=0.26.0` (ABI 15 stable).
  [#30]
- tree-sitter 0.23 → 0.25 (ABI 13 → 15). Harvested from upstream
  nix-community/tree-sitter-nix#145 by @zimbatm. [#4]
- Repo metadata (README badges, Cargo/package.json/tree-sitter.json
  repository URLs) rebranded from `nix-community` to `numtide`. [#25]

### Fixed

- `or` is now a reserved keyword (matching Nix's lexer), accepted only
  in attrpath positions and select-default separators. Previously
  tree-sitter accepted invalid Nix like `let or = 1; in or`. [#31]
- Path scanner rejects consecutive `/` so `a // b` parses as the update
  operator instead of being swallowed as a path token. [#37]
- `#is-not? local` predicate removed from `highlights.scm` — the
  `locals.scm` companion has been all-commented since 2023, so the
  predicate was a no-op that errored on some runtimes (closes #12).
  [#32]
- `build-wasm` script uses `tree-sitter build -w` (the subcommand
  `build-wasm` was removed in tree-sitter 0.25). Harvested from
  upstream nix-community/tree-sitter-nix#155 by @jnoortheen. [#3]
- x86_64-darwin CI runner switched from the retired `macos-13` to
  `macos-15-intel`. Harvested from upstream
  nix-community/tree-sitter-nix#170 by @mdaniels5757. [#1]
- Empty `inherit;` (no attrs) now parses — it's valid Nix. Harvested
  from upstream nix-community/tree-sitter-nix#162 by @TLATER. [#2]
- `nodePackages` attrset removed upstream in nixpkgs 2026-03;
  `shell.nix` / `flake.nix` updated to top-level `pkgs.prettier`,
  `pkgs.node-gyp`. [in #4]
- Grammar nits: dropped redundant `formals` alternative, simplified
  `escape_sequence` regex, fixed `apply_expressionlication` corpus
  typo. [#41]

### Changed (CI / tooling)

- CI migrated from GitHub Actions flake matrix to
  buildbot.numtide.com. All `flake.nix` checks are consumed by
  buildbot-nix directly; the GHA wrapper and `nix-github-actions`
  flake input were removed. `publish.yml` remains on GHA for
  tag-driven crates.io releases. [#43]

### Documentation

- README refreshed with install instructions per ecosystem, editor
  integration notes, development workflow, and release cadence.
- This CHANGELOG started.
- `docs/highlight-groups.md` — reference list of every `@capture`
  name `queries/highlights.scm` produces, for theme authors.

[#1]: https://github.com/numtide/tree-sitter-nix/pull/1
[#2]: https://github.com/numtide/tree-sitter-nix/pull/2
[#3]: https://github.com/numtide/tree-sitter-nix/pull/3
[#4]: https://github.com/numtide/tree-sitter-nix/pull/4
[#12]: https://github.com/numtide/tree-sitter-nix/issues/12
[#14]: https://github.com/numtide/tree-sitter-nix/issues/14
[#25]: https://github.com/numtide/tree-sitter-nix/pull/25
[#26]: https://github.com/numtide/tree-sitter-nix/pull/26
[#27]: https://github.com/numtide/tree-sitter-nix/pull/27
[#28]: https://github.com/numtide/tree-sitter-nix/pull/28
[#29]: https://github.com/numtide/tree-sitter-nix/pull/29
[#30]: https://github.com/numtide/tree-sitter-nix/pull/30
[#31]: https://github.com/numtide/tree-sitter-nix/pull/31
[#32]: https://github.com/numtide/tree-sitter-nix/pull/32
[#33]: https://github.com/numtide/tree-sitter-nix/pull/33
[#34]: https://github.com/numtide/tree-sitter-nix/pull/34
[#35]: https://github.com/numtide/tree-sitter-nix/pull/35
[#36]: https://github.com/numtide/tree-sitter-nix/pull/36
[#37]: https://github.com/numtide/tree-sitter-nix/pull/37
[#38]: https://github.com/numtide/tree-sitter-nix/pull/38
[#39]: https://github.com/numtide/tree-sitter-nix/pull/39
[#40]: https://github.com/numtide/tree-sitter-nix/pull/40
[#41]: https://github.com/numtide/tree-sitter-nix/pull/41
[#43]: https://github.com/numtide/tree-sitter-nix/pull/43
[#45]: https://github.com/numtide/tree-sitter-nix/pull/45
[#48]: https://github.com/numtide/tree-sitter-nix/pull/48
[#49]: https://github.com/numtide/tree-sitter-nix/pull/49
[#50]: https://github.com/numtide/tree-sitter-nix/pull/50
[#52]: https://github.com/numtide/tree-sitter-nix/issues/52
[#53]: https://github.com/numtide/tree-sitter-nix/pull/53
[#55]: https://github.com/numtide/tree-sitter-nix/pull/55
[#56]: https://github.com/numtide/tree-sitter-nix/pull/56
[#57]: https://github.com/numtide/tree-sitter-nix/pull/57
[#58]: https://github.com/numtide/tree-sitter-nix/pull/58
[#59]: https://github.com/numtide/tree-sitter-nix/pull/59

## [0.3.0] — 2025-08-12 (upstream)

Released by nix-community/tree-sitter-nix. Last release before the
numtide fork picked up active maintenance. See upstream's git log for
the full history up to that point.
