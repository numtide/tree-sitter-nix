// Sanitizer parse harness: statically links libtree-sitter (lib.c), parser.c
// and scanner.c, all compiled with -fsanitize=address,undefined, and parses
// every file given on the command line. A sanitizer report aborts the process
// (non-zero exit); a parse that returns no tree, or exceeds --max-ms when set,
// fails the run too.
//
// usage: asan_harness [--report FILE.tsv] [--max-ms N] <file.nix>...
// Output per file: name  bytes  ms  bytes/ms  has_error  error_nodes  max_depth
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <tree_sitter/api.h>

const TSLanguage *tree_sitter_nix(void);

// Iterative walk: pathological inputs nest 50k deep, which would overflow a
// recursive walker.
static unsigned walk(TSNode root, unsigned *maxdepth) {
  TSTreeCursor cur = ts_tree_cursor_new(root);
  unsigned errs = 0, depth = 0;
  for (;;) {
    TSNode n = ts_tree_cursor_current_node(&cur);
    if (ts_node_is_error(n) || ts_node_is_missing(n))
      errs++;
    if (depth > *maxdepth)
      *maxdepth = depth;
    if (ts_tree_cursor_goto_first_child(&cur)) {
      depth++;
      continue;
    }
    while (!ts_tree_cursor_goto_next_sibling(&cur)) {
      if (!ts_tree_cursor_goto_parent(&cur)) {
        ts_tree_cursor_delete(&cur);
        return errs;
      }
      depth--;
    }
  }
}

int main(int argc, char **argv) {
  const char *report = NULL;
  double max_ms = 0;
  int first = 1;
  for (; first < argc; first++) {
    if (!strcmp(argv[first], "--report") && first + 1 < argc)
      report = argv[++first];
    else if (!strcmp(argv[first], "--max-ms") && first + 1 < argc)
      max_ms = atof(argv[++first]);
    else
      break;
  }
  if (first >= argc) {
    fprintf(stderr,
            "usage: asan_harness [--report FILE] [--max-ms N] <file.nix>...\n");
    return 2;
  }
  FILE *rep = report ? fopen(report, "w") : NULL;
  if (report && !rep) {
    perror(report);
    return 2;
  }
  if (rep)
    fprintf(
        rep,
        "file\tbytes\tms\tbytes_per_ms\thas_error\terror_nodes\tmax_depth\n");
  TSParser *p = ts_parser_new();
  ts_parser_set_language(p, tree_sitter_nix());
  int rc = 0;
  unsigned nfiles = 0;
  double slowest = 0;
  const char *slowest_name = "";
  for (int i = first; i < argc; i++) {
    FILE *f = fopen(argv[i], "rb");
    if (!f) {
      perror(argv[i]);
      rc = 1;
      continue;
    }
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc(len + 1);
    size_t got = fread(buf, 1, len, f);
    buf[got] = 0;
    fclose(f);
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    TSTree *t = ts_parser_parse_string(p, NULL, buf, (uint32_t)got);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double ms = (t1.tv_sec - t0.tv_sec) * 1e3 + (t1.tv_nsec - t0.tv_nsec) / 1e6;
    if (!t) {
      fprintf(stderr, "FAIL %s: parser returned no tree\n", argv[i]);
      rc = 1;
      free(buf);
      continue;
    }
    TSNode root = ts_tree_root_node(t);
    unsigned maxdepth = 0, errs = walk(root, &maxdepth);
    if (rep)
      fprintf(rep, "%s\t%zu\t%.3f\t%.1f\t%u\t%u\t%u\n", argv[i], got, ms,
              ms > 0 ? got / ms : 0.0, ts_node_has_error(root) ? 1 : 0, errs,
              maxdepth);
    if (ms > slowest) {
      slowest = ms;
      slowest_name = argv[i];
    }
    if (max_ms > 0 && ms > max_ms) {
      fprintf(stderr, "FAIL %s: %.1f ms > %.0f ms\n", argv[i], ms, max_ms);
      rc = 1;
    }
    ts_tree_delete(t);
    free(buf);
    nfiles++;
  }
  ts_parser_delete(p);
  if (rep)
    fclose(rep);
  printf("asan: %u files parsed, slowest %.1f ms (%s)%s\n", nfiles, slowest,
         slowest_name, rc ? " FAIL" : " OK");
  return rc;
}
