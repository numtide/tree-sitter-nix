# tree-sitter-nix

<img alt="tree-sitter-nix" src="https://banner.numtide.com/banner/numtide/tree-sitter-nix.svg">

[![Support](https://img.shields.io/badge/Support-%23numtide-blue)](https://matrix.to/#/#numtide:numtide.com)

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
  `tags.scm`, `indents.scm`, `folds.scm`, all used by editors that consume tree-sitter.
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
- **crates.io** — `publish.yml` attempts to publish `tree-sitter-nix`
  on every tag push (idempotent: an already-published version is
  skipped). This only works while the org `CRATES_IO_TOKEN` belongs to
  a crate owner; the alternative is a numtide-scoped name, tracked in
  [#14](https://github.com/numtide/tree-sitter-nix/issues/14).
- **PyPI / npm** — planned under a numtide-scoped name (existing
  packages under the bare name are controlled by upstream). Tracking
  in [#14](https://github.com/numtide/tree-sitter-nix/issues/14).

### Release artifacts and provenance

Starting with the first tag after v0.5.0, each GitHub release carries
four assets (v0.4.0 and v0.5.0 predate the asset jobs and have none):

| asset                           | what it is                                                                                                                |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `tree-sitter-nix.wasm`          | parser for web-tree-sitter consumers                                                                                      |
| `tree-sitter-nix.wasm.sha256`   | `sha256sum` sidecar; its `#` comment lines record the exact `tree-sitter-cli` and emscripten versions that built the blob |
| `tree-sitter-nix.tar.gz`        | source tarball with a stable hash (unlike GitHub's auto-generated `/archive/...` tarballs, which may be re-compressed)    |
| `tree-sitter-nix.tar.gz.sha256` | `sha256sum` sidecar; records the commit the tarball was built from                                                        |

The `.wasm` is built with the tree-sitter CLI that generated
`src/parser.c` (currently 0.25.10, with emscripten 4.0.4 — the pair is
asserted in CI). The digest of a tree-sitter WASM build depends on the
CLI version, so a `.wasm` you build yourself with a different CLI will
have a different hash from the released one even though it parses
identically; compare against the CLI named in the sidecar.

To check an asset you downloaded (the sidecars are plain `sha256sum`
output, comments included):

```bash
sha256sum -c --strict tree-sitter-nix.wasm.sha256
sha256sum -c --strict tree-sitter-nix.tar.gz.sha256
```

Both the `.wasm` and the tarball carry [SLSA build provenance attestations](https://slsa.dev/provenance)
signed via [Sigstore](https://www.sigstore.dev/) and recorded in the
public Rekor transparency log. To verify an artifact was built by
this repo's CI from the tagged commit:

```bash
gh attestation verify tree-sitter-nix.wasm --repo numtide/tree-sitter-nix
gh attestation verify tree-sitter-nix.tar.gz --repo numtide/tree-sitter-nix
```

If the artifact was tampered with after publication, or built outside
the official CI, verification fails. Requires `gh` ≥ 2.49. The crate
on crates.io is not attested (crates.io has its own provenance
roadmap).

How a release is cut: push the tag; `publish.yml` builds and checks
everything, creates the GitHub release as a **draft** if nobody has
created it yet, uploads the assets, and ends with a `verify-release`
job that re-downloads the assets and fails if any asset, checksum, or
attestation is missing. A maintainer then edits the notes and
publishes the draft. To exercise the whole pipeline without releasing
anything, dispatch it against an existing tag:

```bash
gh workflow run publish.yml -f tag=v0.5.0
```

That run builds from the tag and reports (as warnings) what the tag's
release is missing.

## Acknowledgements

Original grammar by [Charles Strahan](https://www.cstrahan.com/) and
maintainers of [nix-community/tree-sitter-nix](https://github.com/nix-community/tree-sitter-nix).
This fork preserves commit authorship on all harvested contributions
where possible.

## License

MIT. See [LICENSE](LICENSE).
