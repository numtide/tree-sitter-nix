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

  inline: ($) => [],

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

    // Operator-expression hierarchy.
    //
    // Equality (`==`, `!=`) and comparison (`<`, `<=`, `>`, `>=`) are
    // *non-associative* in Nix's bison grammar:
    //
    //   %nonassoc EQ NEQ              # one tier
    //   %nonassoc '<' '>' LEQ GEQ     # higher tier
    //
    // Tree-sitter's `prec()` does not enforce non-associativity, so we
    // encode it structurally with two intermediate hidden rules:
    //
    //   _expr_op           — anything, including equality/comparison
    //   _expr_op_no_eq     — excludes equality (== !=)
    //   _expr_op_no_cmp    — excludes both equality AND comparison
    //
    // An equality's operands are `_expr_op_no_eq` (so `a == b == c`
    // errors but `a == b < c` parses, since `<` is a tier above).
    // A comparison's operands are `_expr_op_no_cmp` (so `a < b < c`
    // errors).
    //
    // Both rules alias to `binary_expression` so the public AST node
    // type is unchanged. To chain comparisons, parenthesize:
    // `(a == b) == c`.
    _expr_op: ($) =>
      choice(
        alias($._equality_expression, $.binary_expression),
        $._expr_op_no_eq,
      ),

    _expr_op_no_eq: ($) =>
      choice(
        alias($._comparison_expression, $.binary_expression),
        $._expr_op_no_cmp,
      ),

    _expr_op_no_cmp: ($) =>
      choice(
        $.has_attr_expression,
        $.unary_expression,
        $.binary_expression,
        $._expr_apply_expression,
      ),

    // I choose to *not* have this among the binary operators because
    // this is the sole exception that takes an attrpath (instead of expression)
    // as its right operand.
    // My gut feeling is that this is:
    //   1) better in theory, and
    //   2) will be easier to work with in practice.
    has_attr_expression: ($) =>
      prec(
        PREC["?"],
        seq(
          field("expression", $._expr_op),
          field("operator", "?"),
          field("attrpath", $.attrpath),
        ),
      ),

    unary_expression: ($) =>
      choice(
        ...[
          ["!", PREC.not],
          ["-", PREC.negate],
        ].map(([operator, precedence]) =>
          prec(
            precedence,
            seq(field("operator", operator), field("argument", $._expr_op)),
          ),
        ),
      ),

    // Equality (`==`, `!=`) — operands exclude equality.
    // `prec.left` only resolves the LR-table shift/reduce conflict at
    // generate time; it does not change the language accepted.
    _equality_expression: ($) =>
      choice(
        ...[
          ["==", PREC.eq],
          ["!=", PREC.neq],
        ].map(([operator, precedence]) =>
          prec.left(
            precedence,
            seq(
              field("left", $._expr_op_no_eq),
              field("operator", operator),
              field("right", $._expr_op_no_eq),
            ),
          ),
        ),
      ),

    // Comparison (`<`, `<=`, `>`, `>=`) — operands exclude both
    // equality and comparison.
    _comparison_expression: ($) =>
      choice(
        ...[
          ["<", PREC["<"]],
          ["<=", PREC.leq],
          [">", PREC[">"]],
          [">=", PREC.geq],
        ].map(([operator, precedence]) =>
          prec.left(
            precedence,
            seq(
              field("left", $._expr_op_no_cmp),
              field("operator", operator),
              field("right", $._expr_op_no_cmp),
            ),
          ),
        ),
      ),

    // Associative operators (left or right). Operands are the full
    // `_expr_op` so they CAN be comparison expressions, e.g.
    // `a == b && c == d`.
    binary_expression: ($) =>
      choice(
        // left assoc.
        ...[
          ["&&", PREC.and],
          ["||", PREC.or],
          ["|>", PREC.piper],
          ["+", PREC["+"]],
          ["-", PREC["-"]],
          ["*", PREC["*"]],
          ["/", PREC["/"]],
        ].map(([operator, precedence]) =>
          prec.left(
            precedence,
            seq(
              field("left", $._expr_op),
              field("operator", operator),
              field("right", $._expr_op),
            ),
          ),
        ),
        // right assoc.
        ...[
          ["<|", PREC.pipel],
          ["->", PREC.impl],
          ["//", PREC.update],
          ["++", PREC.concat],
        ].map(([operator, precedence]) =>
          prec.right(
            precedence,
            seq(
              field("left", $._expr_op),
              field("operator", operator),
              field("right", $._expr_op),
            ),
          ),
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
