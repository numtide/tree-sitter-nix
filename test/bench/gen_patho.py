#!/usr/bin/env python3
"""Generate pathological Nix inputs (deep nesting, long operator chains, huge tokens)
and, optionally, split the tree-sitter corpus into one .nix file per example.

usage: gen_patho.py [--profile ci|full] [--corpus DIR] OUTDIR

  ci    (default) sizes that parse in well under a second each even under ASan
  full  the audit's sizes (up to 10 MB tokens and 32k-operator chains); some cases
        take tens of seconds with the current grammar (R1-010, R1-019)

Every case is written to OUTDIR/<name>.nix; corpus examples to OUTDIR/corpus-<file>-<n>.nix.
stdlib only.
"""

import argparse
import os
import re
import sys

PROFILES = {
    "ci": {"chain": (1000, 4000), "nest": (1000, 5000), "long": (100_000, 1_000_000)},
    "full": {"chain": (1000, 2000, 4000, 8000, 16000, 32000), "nest": (1000, 5000, 10000, 20000, 50000),
             "long": (100_000, 1_000_000, 10_000_000)},
}


def cases(profile):
    p = PROFILES[profile]
    out = {}
    for n in p["chain"]:
        out[f"add_chain_{n}"] = "e" + "+e" * n
        out[f"attrpath_chain_{n}"] = "a" + ".b" * n
        out[f"apply_chain_{n}"] = "f" + " a" * n
        out[f"concat_chain_{n}"] = "a" + " ++ a" * n
        out[f"update_chain_{n}"] = "a" + " // a" * n
        out[f"impl_chain_{n}"] = "a" + " -> a" * n
        out[f"pipe_chain_{n}"] = "a" + " |> f" * n
        out[f"plus_plus_garbage_{n}"] = "a " + "+" * n
        out[f"not_chain_{n}"] = "!" * n + "a"
        out[f"neg_chain_{n}"] = "-" * n + "a"
        out[f"neg_space_chain_{n}"] = "- " * n + "a"
        out[f"has_attr_chain_{n}"] = "a" + " ? b" * n
        out[f"select_or_chain_{n}"] = "a" + ".b or a" * n
    for n in p["nest"]:
        out[f"nest_paren_{n}"] = "(" * n + "1" + ")" * n
        out[f"nest_list_{n}"] = "[" * n + "1" + "]" * n
        out[f"nest_attrset_{n}"] = "{a=" * n + "1" + ";}" * n
        out[f"nest_interp_{n}"] = '"${' * n + "1" + '}"' * n
        out[f"nest_lambda_{n}"] = "x: " * n + "x"
        out[f"nest_with_{n}"] = "with a; " * n + "x"
        out[f"nest_let_{n}"] = "let a=1; in " * n + "a"
        out[f"nest_if_{n}"] = "if a then " * n + "1" + " else 2" * n
        out[f"nest_assert_{n}"] = "assert a; " * n + "x"
        out[f"nest_paren_unclosed_{n}"] = "(" * n + "1"
        out[f"nest_list_unclosed_{n}"] = "[" * n + "1"
        out[f"nest_attrset_unclosed_{n}"] = "{a=" * n + "1"
        out[f"nest_interp_unclosed_{n}"] = '"${' * n + "1"
        out[f"nest_close_only_{n}"] = ")" * n
        out[f"nest_brace_close_only_{n}"] = "}" * n
        out[f"nest_neg_paren_{n}"] = "-(" * n + "1" + ")" * n
        out[f"nest_formals_{n}"] = "{a?" * n + "1" + ":1}" * n  # not valid Nix, structural only
        out[f"nest_rec_{n}"] = "rec {a=" * n + "1" + ";}" * n
        out[f"nest_paren_lambda_{n}"] = "(x: " * n + "x" + ")" * n
        out[f"nest_indented_interp_{n}"] = "''${" * n + "1" + "}''" * n
    for n in p["long"]:
        out[f"long_ident_{n}"] = "a" * n
        out[f"long_int_{n}"] = "1" * n
        out[f"long_float_{n}"] = "1." + "1" * n
        out[f"long_string_{n}"] = '"' + "a" * n + '"'
        out[f"long_string_dollars_{n}"] = '"' + "$" * n + '"'
        out[f"long_string_unterminated_{n}"] = '"' + "a" * n
        out[f"long_indented_{n}"] = "''" + "a" * n + "''"
        out[f"long_indented_quotes_{n}"] = "''" + "'" * n + "''"
        out[f"long_indented_dollars_{n}"] = "''" + "$" * n + "''"
        out[f"long_line_comment_{n}"] = "# " + "a" * n + "\n1"
        out[f"long_block_comment_{n}"] = "/* " + "a" * n + " */ 1"
        out[f"long_block_comment_stars_{n}"] = "/* " + "*" * n + " */ 1"
        out[f"long_block_comment_unterminated_{n}"] = "/* " + "a" * n
        out[f"long_doc_comment_{n}"] = "/** " + "a" * n + " */ 1"
        out[f"long_path_{n}"] = "/" + "a/" * (n // 2) + "a"
        out[f"long_path_segment_{n}"] = "/" + "a" * n
        out[f"long_hpath_{n}"] = "~/" + "a" * n
        out[f"long_spath_{n}"] = "<" + "a" * n + ">"
        out[f"long_uri_{n}"] = "http://" + "a" * n
        out[f"long_uri_unterminated_{n}"] = "http:" + "a" * n
        out[f"long_whitespace_{n}"] = " " * n + "1"
        out[f"long_newlines_{n}"] = "\n" * n + "1"
        out[f"long_string_escapes_{n}"] = '"' + "\\n" * (n // 2) + '"'
        out[f"long_string_interp_{n}"] = '"' + "${a}" * (n // 4) + '"'
        out[f"long_nul_{n}"] = "\x00" * n
        out[f"long_garbage_{n}"] = "\xff" * n
        out[f"long_list_{n}"] = "[" + "1 " * (n // 2) + "]"
        out[f"long_attrset_{n}"] = "{" + "a=1;" * (n // 4) + "}"
        out[f"long_inherit_{n}"] = "{inherit " + "a " * (n // 2) + ";}"
        out[f"long_formals_{n}"] = "{" + "a," * (n // 2) + "b}:1"
        out[f"long_ident_dash_{n}"] = "a" + "-" * n
        out[f"long_ident_quote_{n}"] = "a" + "'" * n
        out[f"long_dollar_brace_{n}"] = "${" * (n // 2)
        out[f"long_semicolons_{n}"] = ";" * n
        out[f"long_dots_{n}"] = "a" + "." * n
        out[f"long_slashes_{n}"] = "/" * n
        out[f"long_star_slash_{n}"] = "/*" + "*/" * (n // 2)
    return out


CORPUS_SEP = re.compile(r"^=+\n(.*?)\n=+\n", re.M | re.S)


def corpus_examples(path):
    """Yield (name, input) for every example of a tree-sitter corpus file."""
    text = open(path, encoding="utf-8").read()
    parts = CORPUS_SEP.split(text)
    # parts = [preamble, name1, body1, name2, body2, ...]; body = input, '---', expected
    for i in range(1, len(parts) - 1, 2):
        name, body = parts[i].strip(), parts[i + 1]
        src = body.split("\n---", 1)[0]
        yield name, src


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=PROFILES, default="ci")
    ap.add_argument("--corpus", help="test/corpus directory to split into per-example files")
    ap.add_argument("outdir")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    for old in os.listdir(args.outdir):
        if old.endswith(".nix"):
            os.remove(os.path.join(args.outdir, old))
    n = 0
    for name, s in cases(args.profile).items():
        # surrogateescape keeps the deliberate 0xff garbage bytes as-is
        with open(os.path.join(args.outdir, f"{name}.nix"), "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(s)
        n += 1
    c = 0
    if args.corpus:
        for fn in sorted(os.listdir(args.corpus)):
            if not fn.endswith(".txt"):
                continue
            for i, (_, src) in enumerate(corpus_examples(os.path.join(args.corpus, fn))):
                with open(os.path.join(args.outdir, f"corpus-{fn[:-4]}-{i:03d}.nix"), "w", encoding="utf-8") as f:
                    f.write(src)
                c += 1
    print(f"gen_patho: {n} pathological cases ({args.profile}) + {c} corpus examples in {args.outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
