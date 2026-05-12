# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); version numbers
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `queries/folds.scm` — fold ranges for attrsets, lists, parens,
  formals, indented strings, let/with/if/assert expressions, function
  bodies, apply chains, and block / doc comments. Same fold targets as
  nvim-treesitter's vendored Nix queries plus `parenthesized_expression`,
  `assert_expression`, `apply_expression`, `block_comment`, and
  `doc_comment`. Also exposed as `tree_sitter_nix.FOLDS_QUERY` in the
  Python binding. [#49]
- OCaml bindings under `bindings/ocaml/` — hand-written dune package
  with a self-contained libtree-sitter runtime wrapper (`Parser`,
  `Tree`, `Node` modules). No dependency on ocaml-tree-sitter-core.
  [#40]

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

## [0.3.0] — 2025-08-12 (upstream)

Released by nix-community/tree-sitter-nix. Last release before the
numtide fork picked up active maintenance. See upstream's git log for
the full history up to that point.
