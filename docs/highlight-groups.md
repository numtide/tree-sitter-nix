# Highlight groups emitted by tree-sitter-nix

This is an exhaustive list of the `@capture` names that
`queries/highlights.scm` produces. Editor theme authors can use this to
ensure every capture has a colour mapping.

As of **v0.5.0**, conventions align with the
[nvim-treesitter highlight group catalog](https://neovim.io/doc/user/treesitter.html#treesitter-highlight-groups),
which Helix and most other tree-sitter consumers also recognise. The
archived nvim-treesitter's vendored `runtime/queries/nix/` used these
names — our queries are now directly interchangeable.

## Captures by category

### Comments

| Capture                  | Matches                                                                                                                            |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `@comment`               | Any comment. `comment` is a supertype covering `line_comment` (`# …`), `block_comment` (`/* … */`), and `doc_comment` (`/** … */`) |
| `@comment.documentation` | Specifically `doc_comment` (`/** … */`). Fires in addition to `@comment` so themes that care can distinguish                       |
| `@spell`                 | Applied to comments so nvim's treesitter spellcheck covers them                                                                    |

### Keywords

| Capture                | Matches                                              |
| ---------------------- | ---------------------------------------------------- |
| `@keyword`             | `assert` `in` `inherit` `let` `rec` `with`           |
| `@keyword.conditional` | `if` `then` `else`                                   |
| `@keyword.operator`    | `or` (the `a.b or c` field-access default separator) |
| `@keyword.import`      | `import` in expression position                      |
| `@keyword.exception`   | `abort`, `throw`                                     |

### Literals

| Capture                | Matches                                                                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `@number`              | `(integer_expression)`                                                                                                         |
| `@number.float`        | `(float_expression)`                                                                                                           |
| `@boolean`             | `true`, `false`                                                                                                                |
| `@constant.builtin`    | `null`, `builtins`, `__curPos`, `__currentSystem`, `__currentTime`, `__langVersion`, `__nixPath`, `__nixVersion`, `__storeDir` |
| `@string`              | `(string_expression)` and `(indented_string_expression)`                                                                       |
| `@string.escape`       | Escape sequences inside strings (`\n`, `\\`, `\"`, etc.) and `$` escapes                                                       |
| `@string.special.path` | `(path_expression)` / `(hpath_expression)` / `(spath_expression)`                                                              |
| `@string.special.url`  | `(uri_expression)`                                                                                                             |

### Identifiers

| Capture                       | Matches                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------- |
| `@variable`                   | Any identifier not matched by a more specific rule                                            |
| `@variable.parameter`         | Function parameters — `x` in `x: ...`, `formal.name` in `{ a, b }: ...`                       |
| `@variable.parameter.builtin` | The `...` ellipsis in formals                                                                 |
| `@variable.member`            | Attribute names in `(binding)`, `(select_expression attrpath)`, `(inherit)`, `(inherit_from)` |
| `@function`                   | Function definitions — `f` in `f = x: ...`                                                    |
| `@function.call`              | The thing being applied in `(apply_expression)`                                               |
| `@function.builtin`           | Known builtins in apply position, and any `builtins.*` attribute                              |

### Operators and punctuation

| Capture                  | Matches                                     |
| ------------------------ | ------------------------------------------- |
| `@operator`              | Binary/unary expression operators, `=`, `@` |
| `@punctuation.delimiter` | `;` `.` `,` and the `?` in formal-default   |
| `@punctuation.bracket`   | `(` `)` `[` `]` `{` `}`                     |
| `@punctuation.special`   | `${` and `}` that open/close interpolation  |

## Renames from v0.4.x and earlier

| Old (≤ v0.4.x)                                        | New (≥ v0.5.0)                                 |
| ----------------------------------------------------- | ---------------------------------------------- |
| `@escape`                                             | `@string.escape`                               |
| `@string.special.uri`                                 | `@string.special.url`                          |
| `@keyword` (flat, for `if`/`then`/`else`)             | `@keyword.conditional`                         |
| `@keyword` (flat, for `or`)                           | `@keyword.operator`                            |
| `@variable.builtin` (for `true`/`false`)              | `@boolean`                                     |
| `@variable.builtin` (for `null`, `builtins`, `__*`)   | `@constant.builtin`                            |
| `@function.builtin` (covers `import`/`abort`/`throw`) | `@keyword.import` / `@keyword.exception`       |
| `@function` (for apply functions)                     | `@function.call`                               |
| `@property` (for attrset keys)                        | `@variable.member`                             |
| `@embedded` (interpolation content)                   | removed (injected language's theme takes over) |

Theme authors targeting the old names should add fallback mappings
(e.g. alias `@escape` → `@string.escape`). Most modern tree-sitter
theme distributions already map both forms.

## How the queries are loaded

Editors look up `highlights.scm` through the `tree-sitter.json` grammar
declaration (`highlights: "queries/highlights.scm"`). When consumers
bundle queries alongside the compiled parser (which `tree-sitter init`
auto-wires for python / rust / zig bindings), they get this exact file
— any local modifications should be made upstream in this repo so all
consumers stay in sync.
