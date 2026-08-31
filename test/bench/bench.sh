#!/bin/sh
# Wall-clock benchmark of `tree-sitter parse` over test/bench/sample2000.txt.
#
# usage: bench.sh <parser.so> [<baseline.so>]
#   With a second .so, interleave.py runs the two parsers alternately
#   (A B A B ...) so a load change on the machine hits both equally; that
#   relative comparison is the only one meaningful across machines. (hyperfine
#   is not used: it runs every run of A, then every run of B.)
#   Needs a CLI with `parse --lib-path` (tree-sitter >= 0.27).
#
# env: NIXPKGS  root the sample paths are relative to   (default ../nixpkgs)
#      TS       tree-sitter CLI                          (default tree-sitter)
#      RUNS     rounds, one run per parser each          (default 10, minimum 5)
#      WARMUP   warm-up rounds, not timed                (default 2)
#      RESULTS  output directory                          (default test/bench/results)
#      SAMPLE   file list, paths relative to NIXPKGS      (default test/bench/sample2000.txt)
# Outputs: $RESULTS/bench.json (hyperfine layout, read by compare_bench.py),
#          bench.md, bench-stat.txt (the `parse --stat` totals), bench-stat-full.txt
set -eu

here=$(cd "$(dirname "$0")" && pwd)
so=${1:?usage: bench.sh <parser.so> [<baseline.so>]}
baseline_so=${2:-}
NIXPKGS=${NIXPKGS:-../nixpkgs}
TS=${TS:-tree-sitter}
RUNS=${RUNS:-10}
WARMUP=${WARMUP:-2}
RESULTS=${RESULTS:-$here/results}
SAMPLE=${SAMPLE:-$here/sample2000.txt}

[ "$RUNS" -ge 5 ] || { echo "bench.sh: RUNS must be >= 5 (got $RUNS)" >&2; exit 2; }
[ -d "$NIXPKGS" ] || { echo "bench.sh: NIXPKGS=$NIXPKGS is not a directory" >&2; exit 2; }
"$TS" parse --help 2>/dev/null | grep -q -- '--lib-path' ||
  { echo "bench.sh: $TS lacks 'parse --lib-path' (tree-sitter CLI >= 0.27 is required for bench)" >&2; exit 2; }

mkdir -p "$RESULTS"
abs_list=$RESULTS/sample-abs.txt
sed "s|^|$NIXPKGS/|" "$SAMPLE" > "$abs_list"
missing=$(while read -r f; do [ -f "$f" ] || echo "$f"; done < "$abs_list" | wc -l)
[ "$missing" -eq 0 ] || { echo "bench.sh: $missing sample files missing under $NIXPKGS" >&2; exit 2; }

# --stat gives the parse-only throughput (bytes/ms) and the failed-parse count.
# Not piped: a failing CLI must fail this script with its own message, not leave
# an empty file for compare_bench.py to choke on.
"$TS" parse -q --stat --paths "$abs_list" --lib-path "$so" --lang-name nix > "$RESULTS/bench-stat-full.txt" 2>&1 ||
  { cat "$RESULTS/bench-stat-full.txt" >&2; exit 1; }
grep -E '^Total' "$RESULTS/bench-stat-full.txt" > "$RESULTS/bench-stat.txt" ||
  { echo "bench.sh: no 'Total' line in parse --stat output:" >&2; cat "$RESULTS/bench-stat-full.txt" >&2; exit 1; }
cat "$RESULTS/bench-stat.txt"

set -- "$TS parse -q --paths $abs_list --lib-path $so --lang-name nix"
if [ -n "$baseline_so" ]; then
  set -- "$@" "$TS parse -q --paths $abs_list --lib-path $baseline_so --lang-name nix"
fi
python3 "$here/interleave.py" --warmup "$WARMUP" --runs "$RUNS" \
  --export-json "$RESULTS/bench.json" --export-markdown "$RESULTS/bench.md" "$@"
