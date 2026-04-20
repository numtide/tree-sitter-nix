;; Indent query for Nix.
;; Conventions follow nvim-treesitter (@indent.begin / @indent.end /
;; @indent.branch / @indent.align). Helix re-maps @indent → increase and
;; @indent.end → decrease, so the same file works for both.

;; Nodes that introduce an indentation level: everything that opens a
;; bracketed scope, plus binding-bearing expressions and the ellipsis
;; formals. The closing token is picked up by @indent.end below.
[
  (attrset_expression)
  (rec_attrset_expression)
  (let_attrset_expression)
  (list_expression)
  (parenthesized_expression)
  (formals)
  (binding_set)
  (let_expression)
  (if_expression)
  (function_expression)
  (binary_expression)
  (apply_expression)
  (select_expression)
  (interpolation)
  (indented_string_expression)
  (string_expression)
] @indent.begin

;; Closing brackets end the indentation introduced above.
[
  "}"
  ")"
  "]"
] @indent.end

;; `let ... in ...` — the `in` clause is at the same level as `let`.
(let_expression
  "in" @indent.branch)

;; `if ... then ... else ...` — each keyword starts a new branch at the
;; same outer indent as `if`.
(if_expression
  "then" @indent.branch)
(if_expression
  "else" @indent.branch)

;; Don't re-indent inside interpolation string-fragment content; leave
;; it aligned with its opening brace.
(interpolation) @indent.auto
