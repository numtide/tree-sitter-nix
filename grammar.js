const PREC = {
  pipel: 1,
  piper: 1,
  impl: 2,
  or: 3,
  and: 4,
  eq: 5,
  neq: 5,
  "<": 6,
  ">": 6,
  leq: 6,
  geq: 6,
  update: 7,
  not: 8,
  "+": 9,
  "-": 9,
  "*": 10,
  "/": 10,
  concat: 11,
  "?": 12,
  negate: 13,
};

module.exports = grammar({
  name: "nix",

  extras: ($) => [/\s/, $.comment],

  supertypes: ($) => [$._expression, $.comment],

  // Inline the passthrough precedence connectors. The hybrid operator
  // grammar (#52) keeps only the two NONASSOC tiers as separate
  // structural rules; the rest are flat. The remaining connector rules
  // (`_expr_op`, `_expr_pipe`) are single/low-branching passthroughs
  // whose unit reductions are pure overhead — inlining replaces their
  // usages with copies and removes those reductions. The flat tiers
  // (`_expr_low`, `_expr_high`) are NOT inlined: they have multiple
  // alternatives and inlining them multiplies the state count.
  inline: ($) => [$._expr_op, $._expr_pipe],

  externals: ($) => [
    $.string_fragment,
    $._indented_string_fragment,
    $._path_start,
    $.path_fragment,
    $.dollar_escape,
    $._indented_dollar_escape,
  ],

  word: ($) => $.keyword,

  conflicts: ($) => [],

  rules: {
    source_code: ($) => optional(field("expression", $._expression)),
    _expression: ($) => $._expr_function_expression,

    // Keywords go before identifiers to let them take precedence when both are expected.
    // Workaround before https://github.com/tree-sitter/tree-sitter/pull/246
    keyword: ($) => /if|then|else|let|inherit|in|rec|with|assert|or/,
    identifier: ($) => /[a-zA-Z_][a-zA-Z0-9_\'\-]*/,

    variable_expression: ($) => field("name", $.identifier),
    integer_expression: ($) => /[0-9]+/,
    float_expression: ($) =>
      /(([1-9][0-9]*\.[0-9]*)|(0?\.[0-9]+))([Ee][+-]?[0-9]+)?/,

    path_expression: ($) =>
      seq(
        alias($._path_start, $.path_fragment),
        repeat(
          choice(
            $.path_fragment,
            alias($._immediate_interpolation, $.interpolation),
          ),
        ),
      ),

    // Home path. Inspired by Nix's lexer.l, which has two productions:
    //   HPATH       \~(\/{PATH_CHAR}+)+\/?    e.g. ~/.config
    //   HPATH_START \~\/                       used for ~/${...}
    // The second lets a home path begin with `~/` directly followed by
    // interpolation. We mirror the spirit (not the exact regex shapes —
    // tree-sitter's lexer is generated, not hand-rolled flex) with two
    // alternatives: `~/` + path chars, or a bare `~/` literal followed
    // by mandatory interpolation. Tree-sitter's maximal-munch
    // tokenisation disambiguates: `~/foo` matches the longer regex,
    // `~/${...}` matches the bare literal.
    _hpath_start: ($) => /\~\/[a-zA-Z0-9\._\-\+\/]+/,
    hpath_expression: ($) =>
      choice(
        // ~/<path-chars> [<frag-or-interp>...]
        seq(
          alias($._hpath_start, $.path_fragment),
          repeat(
            choice(
              $.path_fragment,
              alias($._immediate_interpolation, $.interpolation),
            ),
          ),
        ),
        // ~/${...} [<frag-or-interp>...]   (bare hpath start + interpolation)
        seq(
          alias("~/", $.path_fragment),
          alias($._immediate_interpolation, $.interpolation),
          repeat(
            choice(
              $.path_fragment,
              alias($._immediate_interpolation, $.interpolation),
            ),
          ),
        ),
      ),

    spath_expression: ($) => /<[a-zA-Z0-9\._\-\+]+(\/[a-zA-Z0-9\._\-\+]+)*>/,
    uri_expression: ($) =>
      /[a-zA-Z][a-zA-Z0-9\+\-\.]*:[a-zA-Z0-9%\/\?:@\&=\+\$,\-_\.\!\~\*\']+/,

    _expr_function_expression: ($) =>
      choice(
        $.function_expression,
        $.assert_expression,
        $.with_expression,
        $.let_expression,
        $._expr_if,
      ),

    function_expression: ($) =>
      choice(
        seq(
          field("universal", $.identifier),
          ":",
          field("body", $._expr_function_expression),
        ),
        seq(
          field("formals", $.formals),
          ":",
          field("body", $._expr_function_expression),
        ),
        seq(
          field("formals", $.formals),
          "@",
          field("universal", $.identifier),
          ":",
          field("body", $._expr_function_expression),
        ),
        seq(
          field("universal", $.identifier),
          "@",
          field("formals", $.formals),
          ":",
          field("body", $._expr_function_expression),
        ),
      ),

    formals: ($) =>
      choice(
        seq("{", "}"),
        seq(
          "{",
          commaSep1(field("formal", $.formal)),
          optional(seq(",", optional(field("ellipses", $.ellipses)))),
          "}",
        ),
        seq("{", field("ellipses", $.ellipses), "}"),
      ),
    formal: ($) =>
      seq(
        field("name", $.identifier),
        optional(seq("?", field("default", $._expression))),
      ),
    ellipses: ($) => "...",

    assert_expression: ($) =>
      seq(
        "assert",
        field("condition", $._expression),
        ";",
        field("body", $._expr_function_expression),
      ),
    with_expression: ($) =>
      seq(
        "with",
        field("environment", $._expression),
        ";",
        field("body", $._expr_function_expression),
      ),
    let_expression: ($) =>
      seq(
        "let",
        optional($.binding_set),
        "in",
        field("body", $._expr_function_expression),
      ),

    _expr_if: ($) => choice($.if_expression, $._expr_op),

    if_expression: ($) =>
      seq(
        "if",
        field("condition", $._expression),
        "then",
        field("consequence", $._expression),
        "else",
        field("alternative", $._expression),
      ),

    // ====================================================================
    // Operator-expression hierarchy (issue #52)
    //
    // Each precedence tier has its own hidden rule. Precedence and
    // associativity are encoded structurally — by which tier each rule's
    // operands draw from — not by `prec()` annotations, which only resolve
    // shift/reduce conflicts within a single rule (not across rules).
    //
    // This is the textbook layered LR grammar. It mirrors Nix's bison
    // declarations, including the `%nonassoc` levels:
    //
    //   %right IMPL                       -> _expr_impl
    //   %left OR                          -> _expr_or
    //   %left AND                         -> _expr_and
    //   %nonassoc EQ NEQ                  -> _expr_eq      (NONASSOC)
    //   %nonassoc '<' '>' LEQ GEQ         -> _expr_cmp     (NONASSOC)
    //   %right UPDATE                     -> _expr_update
    //   %left NOT                         -> _expr_not     (unary)
    //   %left '+' '-'                     -> _expr_add
    //   %left '*' '/'                     -> _expr_mul
    //   %right CONCAT                     -> _expr_concat
    //   %nonassoc '?'                     -> has_attr      (attrpath RHS)
    //   %nonassoc NEGATE                  -> _expr_negate  (unary)
    //
    // The pipe operators (`|>` left-assoc, `<|` right-assoc) sit BELOW
    // implication.
    //
    // Every rule that produces a binary operator is `alias()`'d to
    // `binary_expression` so the public AST node type is unchanged —
    // existing queries and consumers keep working.
    //
    // Non-assoc tiers (`_expr_eq`, `_expr_cmp`, `has_attr`) constrain BOTH
    // operands to the next-tighter tier, so a chain like `a == b == c`
    // cannot be derived: the left operand of the outer `==` would need to
    // be `_expr_eq`, but `_expr_eq` is excluded.
    // ====================================================================

    // Only the two NONASSOC tiers (== != and < > <= >=) need to be
    // separate structural rules: they constrain their operands to a
    // tighter tier so a chain like `a == b == c` cannot be derived.
    // Everything else is left/right-associative and lives in a flat
    // rule with `prec.left`/`prec.right` — the fast, idiomatic
    // tree-sitter encoding (this is how the grammar worked before #52).
    //
    // The crucial safety distinction vs. PR #51: the `prec` here is
    // INTRA-rule (operators within one flat `choice`), which tree-sitter
    // resolves correctly. PR #51's precedence inversion came from `prec`
    // ACROSS separate rules, which `prec` does not arbitrate.
    //
    // Tiers, lowest to highest precedence:
    //
    //   _expr_pipe : |> <|              (kept separate — |> and <| are
    //                                    mutually exclusive, which a flat
    //                                    rule cannot express)
    //   _expr_low  : -> || &&           (flat, prec 2-4)
    //   _expr_eq   : == !=              (NONASSOC, prec 5)
    //   _expr_cmp  : < > <= >=          (NONASSOC, prec 6)
    //   _expr_high : // ! + - * / ++ ?  unary - (flat, prec 7-13)
    //
    // A plain (operator-free) expression reduces through ~6 tiers
    // instead of ~13, roughly halving the unit-reduction cost that the
    // fully-layered grammar paid on every value.

    _expr_op: ($) => $._expr_pipe,

    // |> (left-assoc) <| (right-assoc) — Nix 2.24+ pipes, lowest prec.
    // Separate l/r productions keep them mutually exclusive: the operand
    // of each is `_expr_low`, which excludes the other pipe, so
    // `1 |> f <| g` is rejected (matching Nix).
    _expr_pipe: ($) =>
      choice(
        alias($._expr_pipe_l, $.binary_expression),
        alias($._expr_pipe_r, $.binary_expression),
        $._expr_low,
      ),
    _expr_pipe_l: ($) =>
      seq(
        field("left", $._expr_pipe),
        field("operator", "|>"),
        field("right", $._expr_low),
      ),
    _expr_pipe_r: ($) =>
      prec.right(
        seq(
          field("left", $._expr_low),
          field("operator", "<|"),
          field("right", $._expr_pipe),
        ),
      ),

    // -> (right, prec 2) || (left, prec 3) && (left, prec 4).
    // Flat rule; operands are `_expr_low` so they chain among themselves
    // and fall through to the nonassoc tiers. Intra-rule prec sorts the
    // three operators.
    _expr_low: ($) =>
      choice(alias($._expr_low_b, $.binary_expression), $._expr_eq),
    _expr_low_b: ($) =>
      choice(
        prec.right(
          PREC.impl,
          seq(
            field("left", $._expr_low),
            field("operator", "->"),
            field("right", $._expr_low),
          ),
        ),
        prec.left(
          PREC.or,
          seq(
            field("left", $._expr_low),
            field("operator", "||"),
            field("right", $._expr_low),
          ),
        ),
        prec.left(
          PREC.and,
          seq(
            field("left", $._expr_low),
            field("operator", "&&"),
            field("right", $._expr_low),
          ),
        ),
      ),

    // == != (NONASSOC, prec 5). Operands are `_expr_cmp` (one tier
    // tighter), so `a == b == c` cannot be derived.
    _expr_eq: ($) =>
      choice(alias($._expr_eq_b, $.binary_expression), $._expr_cmp),
    _expr_eq_b: ($) =>
      seq(
        field("left", $._expr_cmp),
        field("operator", choice("==", "!=")),
        field("right", $._expr_cmp),
      ),

    // < > <= >= (NONASSOC, prec 6). Operands are `_expr_high`.
    _expr_cmp: ($) =>
      choice(alias($._expr_cmp_b, $.binary_expression), $._expr_high),
    _expr_cmp_b: ($) =>
      seq(
        field("left", $._expr_high),
        field("operator", choice("<", ">", "<=", ">=")),
        field("right", $._expr_high),
      ),

    // The high-precedence band: // (right, 7), ! (unary, 8),
    // + - (left, 9), * / (left, 10), ++ (right, 11), ? (12),
    // unary - (13). All flat with operands `_expr_high`; intra-rule
    // prec sorts them. This mirrors the pre-#52 flat grammar, restricted
    // to the operators above the nonassoc band — so it inherits that
    // grammar's correct, conflict-free precedence handling, including
    // the unusual `!` < `+` ordering (`!a + b` is `!(a + b)`,
    // `a + !b` is `a + (!b)`) and the prefix-prefix non-conflict
    // (`-!a`, `!-a`).
    _expr_high: ($) =>
      choice(
        alias($._expr_high_b, $.binary_expression),
        alias($._expr_high_u, $.unary_expression),
        $.has_attr_expression,
        $._expr_apply_expression,
      ),
    _expr_high_b: ($) =>
      choice(
        prec.right(
          PREC.update,
          seq(
            field("left", $._expr_high),
            field("operator", "//"),
            field("right", $._expr_high),
          ),
        ),
        prec.left(
          PREC["+"],
          seq(
            field("left", $._expr_high),
            field("operator", choice("+", "-")),
            field("right", $._expr_high),
          ),
        ),
        prec.left(
          PREC["*"],
          seq(
            field("left", $._expr_high),
            field("operator", choice("*", "/")),
            field("right", $._expr_high),
          ),
        ),
        prec.right(
          PREC.concat,
          seq(
            field("left", $._expr_high),
            field("operator", "++"),
            field("right", $._expr_high),
          ),
        ),
      ),
    _expr_high_u: ($) =>
      choice(
        prec(
          PREC.not,
          seq(field("operator", "!"), field("argument", $._expr_high)),
        ),
        prec(
          PREC.negate,
          seq(field("operator", "-"), field("argument", $._expr_high)),
        ),
      ),

    // ? (prec 12). RHS is an attrpath, not an expression. Left-recursive
    // (`a ? b ? c` is `(a ? b) ? c`) because the attrpath RHS means a
    // following `?` never conflicts.
    has_attr_expression: ($) =>
      prec(
        PREC["?"],
        seq(
          field("expression", $._expr_high),
          field("operator", "?"),
          field("attrpath", $.attrpath),
        ),
      ),

    _expr_apply_expression: ($) =>
      choice($.apply_expression, $._expr_select_expression),

    apply_expression: ($) =>
      seq(
        field("function", $._expr_apply_expression),
        field("argument", $._expr_select_expression),
      ),

    _expr_select_expression: ($) => choice($.select_expression, $._expr_simple),

    select_expression: ($) =>
      choice(
        seq(
          field("expression", $._expr_simple),
          ".",
          field("attrpath", $.attrpath),
        ),
        seq(
          field("expression", $._expr_simple),
          ".",
          field("attrpath", $.attrpath),
          "or",
          field("default", $._expr_select_expression),
        ),
      ),

    _expr_simple: ($) =>
      choice(
        $.variable_expression,
        $.integer_expression,
        $.float_expression,
        $.string_expression,
        $.indented_string_expression,
        $.path_expression,
        $.hpath_expression,
        $.spath_expression,
        $.uri_expression,
        $.parenthesized_expression,
        $.attrset_expression,
        $.let_attrset_expression,
        $.rec_attrset_expression,
        $.list_expression,
      ),

    parenthesized_expression: ($) =>
      seq("(", field("expression", $._expression), ")"),

    attrset_expression: ($) => seq("{", optional($.binding_set), "}"),
    let_attrset_expression: ($) =>
      seq("let", "{", optional($.binding_set), "}"),
    rec_attrset_expression: ($) =>
      seq("rec", "{", optional($.binding_set), "}"),

    string_expression: ($) =>
      seq(
        '"',
        repeat(
          choice(
            $.string_fragment,
            $.interpolation,
            choice(
              $.escape_sequence,
              seq($.dollar_escape, alias("$", $.string_fragment)),
            ),
          ),
        ),
        '"',
      ),

    escape_sequence: ($) => token.immediate(/\\[^$]/), // [^$] also matches newlines.

    indented_string_expression: ($) =>
      seq(
        "''",
        repeat(
          choice(
            alias($._indented_string_fragment, $.string_fragment),
            $.interpolation,
            choice(
              alias($._indented_escape_sequence, $.escape_sequence),
              seq(
                alias($._indented_dollar_escape, $.dollar_escape),
                alias("$", $.string_fragment),
              ),
            ),
          ),
        ),
        "''",
      ),
    _indented_escape_sequence: ($) => token.immediate(/'''|''\\[^$]/), // [^$] also matches newlines.

    binding_set: ($) =>
      repeat1(field("binding", choice($.binding, $.inherit, $.inherit_from))),
    binding: ($) =>
      seq(
        field("attrpath", $.attrpath),
        "=",
        field("expression", $._expression),
        ";",
      ),
    inherit: ($) =>
      seq("inherit", optional(field("attrs", $.inherited_attrs)), ";"),
    inherit_from: ($) =>
      seq(
        "inherit",
        "(",
        field("expression", $._expression),
        ")",
        optional(field("attrs", $.inherited_attrs)),
        ";",
      ),

    attrpath: ($) =>
      sep1(
        field(
          "attr",
          choice(
            $.identifier,
            alias("or", $.identifier),
            $.string_expression,
            $.interpolation,
          ),
        ),
        ".",
      ),

    inherited_attrs: ($) =>
      repeat1(
        field(
          "attr",
          choice(
            $.identifier,
            alias("or", $.identifier),
            $.string_expression,
            $.interpolation,
          ),
        ),
      ),

    _immediate_interpolation: ($) =>
      seq(token.immediate("${"), field("expression", $._expression), "}"),
    interpolation: ($) => seq("${", field("expression", $._expression), "}"),

    list_expression: ($) =>
      seq("[", repeat(field("element", $._expr_select_expression)), "]"),

    // `comment` is a supertype (see `supertypes` above) covering all three
    // Nix comment forms. Consumers matching `(comment)` in queries keep
    // working; consumers introspecting node-type strings now see one of
    // `line_comment`, `block_comment`, `doc_comment`.
    //
    // Regex shapes are taken verbatim from Nix's own flex lexer
    // (`src/libexpr/lexer.l`) so edge cases match the reference parser:
    //   - `/**/`  → block_comment (empty long comment)
    //   - `/***/` → block_comment (three-star long comment, NOT doc)
    //   - `/** */` → doc_comment (RFC 145)
    //   - `/**foo*/` → doc_comment (first body char after `/**` must not
    //     be `/` or `*`)
    comment: ($) => choice($.line_comment, $.block_comment, $.doc_comment),

    line_comment: ($) => token(seq("#", /.*/)),

    // Long/block comment. Body is `([^*]|\*+[^*/])*\*+` per Nix's lexer.l.
    block_comment: ($) => token(seq("/*", /([^*]|\*+[^*\/])*\*+/, "/")),

    // Doc comment. Nix's lexer requires the first body char after `/**`
    // to be neither `/` nor `*` — this excludes `/**/` and `/***/` from
    // being doc comments. Precedence 1 so the longer `/**...*/` match
    // wins over `block_comment` on the shared `/*...*/` prefix.
    doc_comment: ($) =>
      token(prec(1, seq("/**", /[^\/*]([^*]|\*+[^*\/])*\*+/, "/"))),
  },
});

function sep(rule, separator) {
  return optional(sep1(rule, separator));
}

function sep1(rule, separator) {
  return seq(rule, repeat(seq(separator, rule)));
}

function commaSep1(rule) {
  return sep1(rule, ",");
}

function commaSep(rule) {
  return optional(commaSep1(rule));
}
