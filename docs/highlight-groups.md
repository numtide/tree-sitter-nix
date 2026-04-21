# Highlight groups emitted by tree-sitter-nix

This is an exhaustive list of the `@capture` names that
`queries/highlights.scm` produces. Editor theme authors can use this to
ensure every capture has a colour mapping.

Conventions follow [nvim-treesitter's highlight group
catalog](https://neovim.io/doc/user/treesitter.html#treesitter-highlight-groups),
which Helix and most other tree-sitter consumers also recognise.

## Captures by category

### Comments

| Capture    | Matches                                          |
| ---------- | ------------------------------------------------ |
| `@comment` | Any `(comment)` node — `# line` or `/* block */` |

### Keywords and operators

| Capture     | Matches                                                            |
| ----------- | ------------------------------------------------------------------ |
| `@keyword`  | `if` `then` `else` `let` `inherit` `in` `rec` `with` `assert` `or` |
| `@operator` | Binary and unary expression operators                              |

### Literals

| Capture                | Matches                                                                  |
| ---------------------- | ------------------------------------------------------------------------ |
| `@number`              | `(integer_expression)` and `(float_expression)`                          |
| `@string`              | `(string_expression)` and `(indented_string_expression)`                 |
| `@escape`              | Escape sequences inside strings (`\n`, `\\`, `\"`, etc.) and `$` escapes |
| `@string.special.path` | `(path_expression)` / `(hpath_expression)` / `(spath_expression)`        |
| `@string.special.uri`  | `(uri_expression)`                                                       |

### Identifiers

| Capture               | Matches                                                                                                                                                                                                                                                               |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `@variable`           | Identifiers used as value references (filtered via `#not-match?` against the builtin list)                                                                                                                                                                            |
| `@variable.builtin`   | Builtins that resolve to values: `builtins`, `true`, `false`, `null`, `__curPos`, `__currentSystem`, `__currentTime`, `__langVersion`, `__nixPath`, `__nixVersion`, `__storeDir`                                                                                      |
| `@variable.parameter` | Function parameters — the universal `x` in `x: ...` and `formal.name` inside `{ a, b }: ...`                                                                                                                                                                          |
| `@function`           | The function being applied in an `(apply_expression)` — both `foo` in `foo x` and `foo.bar` in `foo.bar x`                                                                                                                                                            |
| `@function.builtin`   | Builtins that resolve to callables in apply position: `__add`, `__map`, `derivation`, `import`, `abort`, `throw`, `fetchGit`, `fetchTarball`, `fetchTree`, `baseNameOf`, `dirOf`, and ~80 other `__`-prefixed builtin functions (full list in `highlights.scm` regex) |
| `@property`           | Attribute names in `(binding)`, `(select_expression attrpath)`, `(inherit)`, `(inherit_from)`                                                                                                                                                                         |

### Punctuation

| Capture                  | Matches                                       |
| ------------------------ | --------------------------------------------- |
| `@punctuation.delimiter` | `;` `.` `,` `=` and the `?` in formal-default |
| `@punctuation.bracket`   | `(` `)` `[` `]` `{` `}`                       |
| `@punctuation.special`   | `${` and `}` that open/close interpolation    |

### Interpolation

| Capture     | Matches                                                                              |
| ----------- | ------------------------------------------------------------------------------------ |
| `@embedded` | The expression body inside `${...}` (rendered according to its own language's theme) |

## Expected divergence from nvim-treesitter's default style

Nvim-treesitter keeps evolving capture naming conventions:

- We currently use `@escape`, but nvim-treesitter newer-style is
  `@string.escape`. Both render via similar theme mappings; consumers
  that care can define the alias.
- We emit `@string.special.uri`; nvim-treesitter master uses
  `@string.special.url`. Minor string semantics difference, both work.

Moving to the newer names is tracked as an independent follow-up so the
diff stays inspectable for downstream theme maintainers.

## How the queries are loaded

Editors look up `highlights.scm` through the `tree-sitter.json` grammar
declaration (`highlights: "queries/highlights.scm"`). When consumers
bundle queries alongside the compiled parser (which `tree-sitter init`
auto-wires for python / rust / zig bindings), they get this exact file
— any local modifications should be made upstream in this repo so all
consumers stay in sync.
