# tree-sitter-nix

[![Build Status](https://github.com/numtide/tree-sitter-nix/actions/workflows/nix-github-actions.yml/badge.svg)](https://github.com/numtide/tree-sitter-nix/actions/workflows/nix-github-actions.yml)

A [tree-sitter](https://github.com/tree-sitter/tree-sitter) grammar for
the [Nix](https://nixos.org/) expression language.

This is a [numtide](https://github.com/numtide) fork of
[nix-community/tree-sitter-nix](https://github.com/nix-community/tree-sitter-nix),
kept moving while upstream is stalled. **New bug reports and PRs should be
filed here.** The grammar itself is fully compatible with upstream
consumers (ABI 15, tree-sitter ≥ 0.26).

## What's in the box

- **Grammar** — `grammar.js` + a custom C scanner for strings / paths /
  interpolation edge cases (`src/scanner.c`).
- **Queries** — `queries/highlights.scm`, `injections.scm`, `locals.scm`,
  `tags.scm`, `indents.scm`, all used by editors that consume tree-sitter.
- **Language bindings** under `bindings/`:
  - `c` — header + pkg-config template
  - `go` — cgo wrapper
  - `node` — N-API bindings + TypeScript declarations
  - `python` — CPython module with bundled queries
  - `rust` — crate exposing `LANGUAGE` const
  - `swift` — SwiftPM target
  - `zig` — Zig module + `build.zig`
  - `ocaml` — OCaml library + opam package (hand-written; see
    [`bindings/ocaml/README.md`](bindings/ocaml/README.md))

## Usage

### In Nix (flakes)

```nix
inputs.tree-sitter-nix.url = "github:numtide/tree-sitter-nix";
```

### In Rust

```toml
[dependencies]
tree-sitter-nix = { git = "https://github.com/numtide/tree-sitter-nix" }
tree-sitter = ">=0.26"
```

```rust
let mut parser = tree_sitter::Parser::new();
parser.set_language(&tree_sitter_nix::LANGUAGE.into())?;
let tree = parser.parse("{ a = 1; }", None).unwrap();
```

### In Node.js

```sh
npm install github:numtide/tree-sitter-nix
```

```js
const Parser = require("tree-sitter");
const Nix = require("tree-sitter-nix");
const parser = new Parser();
parser.setLanguage(Nix);
```

### In Python (local install)

```sh
pip install git+https://github.com/numtide/tree-sitter-nix
```

```python
import tree_sitter_nix
from tree_sitter import Language, Parser
parser = Parser(Language(tree_sitter_nix.language()))
tree = parser.parse(b"{ a = 1; }")
# Queries are also bundled:
# tree_sitter_nix.HIGHLIGHTS_QUERY, .INJECTIONS_QUERY, .LOCALS_QUERY,
# .TAGS_QUERY, .INDENTS_QUERY
```

### Editor integrations

The grammar is automatically picked up by:

- **Neovim** via [nvim-treesitter](https://github.com/nvim-treesitter/nvim-treesitter)
  (`:TSInstall nix`). Our queries follow nvim-treesitter capture conventions.
- **Helix** — `helix-editor/helix` bundles the grammar. For the fork,
  clone into your Helix runtime's `grammars/` directory or use Nix
  overlays pinning this flake.
- **Emacs** via [tree-sitter-langs](https://github.com/emacs-tree-sitter/tree-sitter-langs).
- **Zed**, **GitHub code navigation**, **nixd** / **nil** language servers
  — all consume the C bindings and queries directly.

## Development

### Prerequisites

Everything is managed by the Nix flake:

```sh
nix develop
```

That gives you `tree-sitter`, `node`, `cargo`, formatters, and
editorconfig-checker.

### Common tasks

```sh
# Regenerate parser after editing grammar.js
tree-sitter generate --abi 15

# Run the test suite (corpus + highlight tests)
tree-sitter test

# Run all flake checks (build, generated-diff, treefmt, bindings tests)
nix flake check

# Format everything
nix fmt
```

### Grammar changes

After editing `grammar.js`:

1. Run `tree-sitter generate --abi 15` to regenerate `src/parser.c`,
   `src/grammar.json`, `src/node-types.json`.
2. Run `tree-sitter test`. Add corpus cases under `corpus/` for new
   constructs.
3. When in doubt about whether a construct is valid Nix, check against
   the real C++ parser:
   `nix-instantiate --parse -E '<expression>'`.

### Query changes

`queries/*.scm` files are used at load time by tree-sitter consumers.
Tests in `test/highlight/basic.nix` exercise `highlights.scm` via
`tree-sitter test`.

## Contributing

PRs welcome. Low-friction workflow:

1. Fork (or branch if you have push access), make changes, run
   `tree-sitter test` and `nix flake check` locally.
2. Open a PR; CI runs the flake matrix across Linux (x86_64/aarch64)
   and macOS (x86_64/aarch64).
3. Small fixes and dependency bumps auto-merge on green; larger
   changes get a human review.

### Release cadence

Releases are tagged `vX.Y.Z` on this repo. Consumers using the git URL
will pick up changes on next flake update. Published-registry
strategy:

- **Nix flake** — ready to consume immediately.
- **crates.io / PyPI / npm** — planned under a numtide-scoped name
  (existing packages under the bare name are controlled by upstream).
  Tracking in [#14](https://github.com/numtide/tree-sitter-nix/issues/14).

## Acknowledgements

Original grammar by [Charles Strahan](https://www.cstrahan.com/) and
maintainers of [nix-community/tree-sitter-nix](https://github.com/nix-community/tree-sitter-nix).
This fork preserves commit authorship on all harvested contributions
where possible.

## License

MIT. See [LICENSE](LICENSE).
