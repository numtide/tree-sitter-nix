#!/bin/sh
# Tree memory and shape: bytes/node, hidden internal nodes (rawwalk) and RSS
# with one reused TSParser over a file list.
#
# usage: memory.sh <mem_harness> <parser.so>
#
# env: NIXPKGS  root the list paths are relative to           (default ../nixpkgs)
#      LIST     file list relative to NIXPKGS, or "full" for  (default test/bench/sample2000.txt)
#               every .nix under NIXPKGS (the audit's 44492)
#      RAWWALK  path to the rawwalk binary, empty to skip     (default: skip)
#      RESULTS  output directory                              (default test/bench/results)
# Outputs: $RESULTS/memory-files.tsv, memory-summary.txt, memory-rss.tsv, memory-rawwalk.txt
set -eu

here=$(cd "$(dirname "$0")" && pwd)
harness=${1:?usage: memory.sh <mem_harness> <parser.so>}
so=${2:?usage: memory.sh <mem_harness> <parser.so>}
NIXPKGS=${NIXPKGS:-../nixpkgs}
LIST=${LIST:-$here/sample2000.txt}
RAWWALK=${RAWWALK:-}
RESULTS=${RESULTS:-$here/results}

[ -d "$NIXPKGS" ] || { echo "memory.sh: NIXPKGS=$NIXPKGS is not a directory" >&2; exit 2; }
mkdir -p "$RESULTS"
abs_list=$RESULTS/memory-abs.txt
if [ "$LIST" = full ]; then
  find "$NIXPKGS" -name '*.nix' -type f | LC_ALL=C sort > "$abs_list"
  list_name="full nixpkgs ($(wc -l < "$abs_list") files)"
else
  sed "s|^|$NIXPKGS/|" "$LIST" > "$abs_list"
  list_name=$LIST
  # a missing file would silently shrink the measured set below the baseline's
  missing=$(while read -r f; do [ -f "$f" ] || echo "$f"; done < "$abs_list" | wc -l)
  [ "$missing" -eq 0 ] || { echo "memory.sh: $missing list files missing under $NIXPKGS" >&2; exit 2; }
fi
echo "list: $list_name" | tee "$RESULTS/memory-summary.txt"

# stats: per-file TSV on stdout, '#key<TAB>value' totals on stderr
"$harness" stats "$so" "$abs_list" > "$RESULTS/memory-files.tsv" 2>> "$RESULTS/memory-summary.txt"
grep '^#' "$RESULTS/memory-summary.txt"

# reuse: RSS of one parser reused over the whole list (leak check + peak RSS)
"$harness" reuse "$so" "$abs_list" 0 > "$RESULTS/memory-rss.tsv"
tail -n 2 "$RESULTS/memory-rss.tsv"

if [ -n "$RAWWALK" ] && [ -x "$RAWWALK" ]; then
  "$RAWWALK" "$so" "$abs_list" > "$RESULTS/memory-rawwalk.txt"
  head -n 2 "$RESULTS/memory-rawwalk.txt"
else
  rm -f "$RESULTS/memory-rawwalk.txt"
  echo "rawwalk skipped (needs TREE_SITTER_SRC private headers): no hidden-node count"
fi
