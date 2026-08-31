// Memory / tree-shape harness for tree-sitter-nix against libtree-sitter.
//
// Build (see Makefile target build/mem_harness):
//   cc -O2 -std=gnu11 -I<ts>/lib/include harness.c build/libtree-sitter.o \
//      -ldl -lpthread -o mem_harness
//
// mem_harness stats <lang.so> <listfile>
//   per-file TSV on stdout; '#key<TAB>value' totals and per-symbol counts on
//   stderr
// mem_harness reuse <lang.so> <listfile> <fresh>
//   RSS / live bytes while parsing the whole list with one parser (fresh=0)
//   or a new parser per file (fresh=1)
//
// Tree bytes are measured by installing a counting allocator with
// ts_set_allocator, so they are exactly what libtree-sitter keeps alive for the
// tree (not RSS, which includes malloc slack).
#define _GNU_SOURCE
#include <dlfcn.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <tree_sitter/api.h>

static size_t live_bytes = 0, peak_live = 0, total_alloc = 0, n_alloc = 0;

static void account(void *p, int sign) {
  if (!p)
    return;
  size_t s = malloc_usable_size(p);
  if (sign > 0) {
    live_bytes += s;
    total_alloc += s;
    n_alloc++;
    if (live_bytes > peak_live)
      peak_live = live_bytes;
  } else {
    live_bytes -= s;
  }
}
static void *c_malloc(size_t n) {
  void *p = malloc(n);
  account(p, 1);
  return p;
}
static void *c_calloc(size_t a, size_t b) {
  void *p = calloc(a, b);
  account(p, 1);
  return p;
}
static void *c_realloc(void *p, size_t n) {
  account(p, -1);
  void *q = realloc(p, n);
  account(q, 1);
  return q;
}
static void c_free(void *p) {
  account(p, -1);
  free(p);
}

static double now_ms(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}
static long rss_kb(void) {
  FILE *f = fopen("/proc/self/status", "r");
  char line[256];
  long v = -1;
  while (f && fgets(line, sizeof line, f))
    if (sscanf(line, "VmRSS: %ld", &v) == 1)
      break;
  if (f)
    fclose(f);
  return v;
}
static long peak_rss_kb(void) {
  struct rusage ru;
  getrusage(RUSAGE_SELF, &ru);
  return ru.ru_maxrss;
}
static char *slurp(const char *path, size_t *len) {
  FILE *f = fopen(path, "rb");
  if (!f)
    return NULL;
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  fseek(f, 0, SEEK_SET);
  char *b = malloc(n + 1);
  size_t r = fread(b, 1, n, f);
  fclose(f);
  b[r] = 0;
  *len = r;
  return b;
}

typedef struct {
  uint64_t named, anon, error, missing, extra, total, max_depth;
  uint64_t *per_sym;
} Counts;

// Cursor walk: recursion depth equals tree depth, which is bounded by nesting,
// not file size.
static void walk(TSTreeCursor *cur, Counts *c, uint32_t depth) {
  TSNode n = ts_tree_cursor_current_node(cur);
  c->total++;
  if (depth > c->max_depth)
    c->max_depth = depth;
  if (ts_node_is_missing(n))
    c->missing++;
  if (ts_node_is_error(n))
    c->error++;
  if (ts_node_is_extra(n))
    c->extra++;
  if (ts_node_is_named(n))
    c->named++;
  else
    c->anon++;
  c->per_sym[ts_node_symbol(n)]++;
  if (ts_tree_cursor_goto_first_child(cur)) {
    do
      walk(cur, c, depth + 1);
    while (ts_tree_cursor_goto_next_sibling(cur));
    ts_tree_cursor_goto_parent(cur);
  }
}

static const TSLanguage *load(const char *so) {
  void *h = dlopen(so, RTLD_NOW);
  if (!h) {
    fprintf(stderr, "dlopen: %s\n", dlerror());
    exit(2);
  }
  const TSLanguage *(*fn)(void) = dlsym(h, "tree_sitter_nix");
  if (!fn) {
    fprintf(stderr, "no tree_sitter_nix symbol in %s\n", so);
    exit(2);
  }
  return fn();
}

static int cmd_stats(const TSLanguage *lang, const char *list) {
  FILE *lf = fopen(list, "r");
  if (!lf) {
    perror(list);
    return 2;
  }
  uint32_t nsym = ts_language_symbol_count(lang);
  uint64_t *tot = calloc(nsym, sizeof *tot);
  Counts agg = {0};
  agg.per_sym = tot;
  TSParser *p = ts_parser_new();
  ts_parser_set_language(p, lang);
  printf("file\tbytes\tnodes\tnamed\tanon\terror\tmissing\textra\tdepth\ttree_"
         "bytes\tparser_retained\tpeak_extra_bytes\tparse_us\n");
  char path[4096];
  uint64_t files = 0, skipped = 0, src_bytes = 0, tree_bytes_sum = 0;
  double us_sum = 0;
  while (fgets(path, sizeof path, lf)) {
    path[strcspn(path, "\n")] = 0;
    size_t len;
    char *src = slurp(path, &len);
    if (!src) {
      // counted and reported, never silent: a wrong NIXPKGS would otherwise
      // just measure fewer files than the baseline
      skipped++;
      continue;
    }
    size_t before = live_bytes;
    peak_live = live_bytes;
    double t0 = now_ms();
    TSTree *t = ts_parser_parse_string(p, NULL, src, len);
    double us = (now_ms() - t0) * 1000.0;
    size_t after_parse = live_bytes, peak_extra = peak_live - before;
    Counts c = {0};
    c.per_sym = calloc(nsym, sizeof *c.per_sym);
    TSTreeCursor cur = ts_tree_cursor_new(ts_tree_root_node(t));
    walk(&cur, &c, 0);
    ts_tree_cursor_delete(&cur);
    for (uint32_t i = 0; i < nsym; i++)
      tot[i] += c.per_sym[i];
    agg.total += c.total;
    agg.named += c.named;
    agg.anon += c.anon;
    agg.error += c.error;
    agg.missing += c.missing;
    agg.extra += c.extra;
    free(c.per_sym);
    ts_tree_delete(t);
    free(src);
    // live_bytes now holds only what the parser retained across the parse
    size_t tree_bytes = after_parse - live_bytes,
           parser_retained = live_bytes - before;
    printf("%s\t%zu\t%llu\t%llu\t%llu\t%llu\t%llu\t%llu\t%llu\t%zu\t%zu\t%zu\t%"
           ".0f\n",
           path, len, (unsigned long long)c.total, (unsigned long long)c.named,
           (unsigned long long)c.anon, (unsigned long long)c.error,
           (unsigned long long)c.missing, (unsigned long long)c.extra,
           (unsigned long long)c.max_depth, tree_bytes, parser_retained,
           peak_extra, us);
    files++;
    src_bytes += len;
    tree_bytes_sum += tree_bytes;
    us_sum += us;
  }
  fprintf(stderr,
          "#files\t%llu\n#skipped\t%llu\n#src_bytes\t%llu\n#tree_bytes\t%llu\n#"
          "nodes\t%llu\n#named\t%llu\n#anon\t%llu\n"
          "#error\t%llu\n#missing\t%llu\n#extra\t%llu\n#parse_ms\t%.1f\n#bytes_"
          "per_ms\t%.0f\n"
          "#tree_bytes_per_src_byte\t%.3f\n#bytes_per_node\t%.1f\n",
          (unsigned long long)files, (unsigned long long)skipped,
          (unsigned long long)src_bytes, (unsigned long long)tree_bytes_sum,
          (unsigned long long)agg.total, (unsigned long long)agg.named,
          (unsigned long long)agg.anon, (unsigned long long)agg.error,
          (unsigned long long)agg.missing, (unsigned long long)agg.extra,
          us_sum / 1000.0, src_bytes / (us_sum / 1000.0),
          (double)tree_bytes_sum / src_bytes,
          (double)tree_bytes_sum / agg.total);
  for (uint32_t i = 0; i < nsym; i++)
    if (tot[i]) {
      TSSymbolType ty = ts_language_symbol_type(lang, i);
      fprintf(stderr, "sym\t%s\t%s\t%llu\n", ts_language_symbol_name(lang, i),
              ty == TSSymbolTypeRegular     ? "named"
              : ty == TSSymbolTypeAnonymous ? "anon"
              : ty == TSSymbolTypeSupertype ? "super"
                                            : "aux",
              (unsigned long long)tot[i]);
    }
  ts_parser_delete(p);
  free(tot);
  return 0;
}

static int cmd_reuse(const TSLanguage *lang, const char *list, int fresh) {
  FILE *lf = fopen(list, "r");
  if (!lf) {
    perror(list);
    return 2;
  }
  TSParser *p = fresh ? NULL : ts_parser_new();
  if (p)
    ts_parser_set_language(p, lang);
  char path[4096];
  uint64_t files = 0, skipped = 0;
  printf("files\trss_kb\tlive_bytes\tpeak_live\ttotal_alloc\tn_alloc\n");
  printf("%llu\t%ld\t%zu\t%zu\t%zu\t%zu\n", 0ULL, rss_kb(), live_bytes,
         peak_live, total_alloc, n_alloc);
  while (fgets(path, sizeof path, lf)) {
    path[strcspn(path, "\n")] = 0;
    size_t len;
    char *src = slurp(path, &len);
    if (!src) {
      skipped++;
      continue;
    }
    TSParser *q = p;
    if (fresh) {
      q = ts_parser_new();
      ts_parser_set_language(q, lang);
    }
    TSTree *t = ts_parser_parse_string(q, NULL, src, len);
    ts_tree_delete(t);
    free(src);
    if (fresh)
      ts_parser_delete(q);
    files++;
    if (files % 4000 == 0)
      printf("%llu\t%ld\t%zu\t%zu\t%zu\t%zu\n", (unsigned long long)files,
             rss_kb(), live_bytes, peak_live, total_alloc, n_alloc);
  }
  printf("%llu\t%ld\t%zu\t%zu\t%zu\t%zu\n", (unsigned long long)files, rss_kb(),
         live_bytes, peak_live, total_alloc, n_alloc);
  if (p)
    ts_parser_delete(p);
  printf("after_parser_delete\t%ld\t%zu\t%zu\t%zu\t%zu\n", rss_kb(), live_bytes,
         peak_live, total_alloc, n_alloc);
  printf("peak_rss_kb\t%ld\n", peak_rss_kb());
  if (skipped)
    fprintf(stderr, "reuse: %llu unreadable file(s) skipped\n",
            (unsigned long long)skipped);
  return 0;
}

int main(int argc, char **argv) {
  if (argc < 4) {
    fprintf(stderr,
            "usage: %s stats <lang.so> <listfile> | reuse <lang.so> <listfile> "
            "<fresh:0|1>\n",
            argv[0]);
    return 2;
  }
  ts_set_allocator(c_malloc, c_calloc, c_realloc, c_free);
  const TSLanguage *lang = load(argv[2]);
  if (!strcmp(argv[1], "stats"))
    return cmd_stats(lang, argv[3]);
  if (!strcmp(argv[1], "reuse"))
    return cmd_reuse(lang, argv[3], argc > 4 ? atoi(argv[4]) : 0);
  fprintf(stderr, "unknown mode %s\n", argv[1]);
  return 2;
}
