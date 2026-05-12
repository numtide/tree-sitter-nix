; Fold ranges for Nix.
;
; Nix has no syntactic block construct (no `{ ... }` statement blocks)
; — every region is an expression. The folds below cover the
; expression forms that are commonly multi-line in real Nix code.
;
; Convention follows nvim-treesitter / Helix: each captured node's full
; range becomes a fold region. Editors typically trim the first line so
; the opening token stays visible.

[
  ; Bracketed expression scopes.
  (attrset_expression)
  (rec_attrset_expression)
  (let_attrset_expression)
  (list_expression)
  (parenthesized_expression)
  (formals)

  ; Long literal forms.
  (indented_string_expression)
  (string_expression)

  ; Binding-bearing expressions — `let … in …`, `with …; …`, `if … then
  ; … else …`. These are often the biggest single regions in a flake.
  (let_expression)
  (with_expression)
  (if_expression)
  (assert_expression)

  ; Function bodies.
  (function_expression)

  ; Long apply chains (e.g. derivation calls with many positional args).
  (apply_expression)
] @fold

; Comments — fold long block / doc comments, but not single-line ones.
[
  (block_comment)
  (doc_comment)
] @fold
