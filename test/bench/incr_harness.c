// Incremental-parsing differential harness: for every file and every generated
// edit, the tree produced by an incremental reparse (old tree + ts_tree_edit)
// must equal the tree produced by a fresh parse of the same text. Any
// difference is a parser bug (R2-009 class), dumped to
// <out>/mismatch-N.{incr.txt,full.txt,new.nix,meta}.
//
// usage: incr_harness [--npos N] [--max-mismatches M] [--out DIR] [--files
// LIST] <lang.so> [file...]
//   --npos N           edit positions per file, evenly spaced (default 10)
//   --max-mismatches M exit 1 when more than M edits mismatch (default 0)
//   --out DIR          where mismatch dumps and summary.json go (default .)
//   --files LIST       newline-separated file list, in addition to positional
//   files
// Per position: insert "x", delete 1, replace 1 by "x", insert each Nix
// delimiter
// ('' ${ / " # \n } { space ' $ \ /* */) and delete 2 bytes.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <tree_sitter/api.h>

typedef struct {
  char *buf;
  size_t len, cap;
} SB;
static void sb_put(SB *s, const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  char tmp[512];
  int n = vsnprintf(tmp, sizeof tmp, fmt, ap);
  va_end(ap);
  if (n < 0)
    return;
  if ((size_t)n >= sizeof tmp)
    n = sizeof tmp - 1;
  if (s->len + n + 1 > s->cap) {
    s->cap = (s->cap + n + 1) * 2;
    s->buf = realloc(s->buf, s->cap);
  }
  memcpy(s->buf + s->len, tmp, n);
  s->len += n;
  s->buf[s->len] = 0;
}

static TSPoint point_at(const char *text, uint32_t byte) {
  TSPoint p = {0, 0};
  for (uint32_t i = 0; i < byte; i++) {
    if (text[i] == '\n') {
      p.row++;
      p.column = 0;
    } else
      p.column++;
  }
  return p;
}

// Full structural dump: type, missing/anon flags, byte span, field names. Two
// trees are considered equal iff their dumps are byte-identical.
static void dump(TSNode n, SB *s, int depth) {
  sb_put(s, "%*s(%s%s%s %u-%u", depth, "", ts_node_type(n),
         ts_node_is_missing(n) ? " MISSING" : "",
         ts_node_is_named(n) ? "" : " anon", ts_node_start_byte(n),
         ts_node_end_byte(n));
  uint32_t c = ts_node_child_count(n);
  for (uint32_t i = 0; i < c; i++) {
    const char *f = ts_node_field_name_for_child(n, i);
    if (f)
      sb_put(s, "\n%*s%s:", depth + 1, "", f);
    else
      sb_put(s, "\n");
    dump(ts_node_child(n, i), s, depth + 1);
  }
  sb_put(s, ")");
}

typedef struct {
  const char *kind;
  uint32_t pos, del;
  const char *ins;
} Edit;

static const char *outdir = ".";
static uint64_t n_edits = 0, n_mismatch = 0;

static void write_file(const char *name, int no, const char *ext,
                       const char *data, size_t len) {
  char p[4096];
  snprintf(p, sizeof p, "%s/%s-%d.%s", outdir, name, no, ext);
  FILE *f = fopen(p, "w");
  if (!f) {
    perror(p);
    return;
  }
  fwrite(data, 1, len, f);
  fclose(f);
}

static void run_edit(TSParser *parser, const char *file, const char *text,
                     uint32_t len, TSTree *old, Edit ed) {
  uint32_t inslen = strlen(ed.ins);
  if (ed.pos > len)
    return;
  if (ed.pos + ed.del > len)
    ed.del = len - ed.pos;
  uint32_t nlen = len - ed.del + inslen;
  char *nt = malloc(nlen + 1);
  memcpy(nt, text, ed.pos);
  memcpy(nt + ed.pos, ed.ins, inslen);
  memcpy(nt + ed.pos + inslen, text + ed.pos + ed.del, len - ed.pos - ed.del);
  nt[nlen] = 0;
  TSInputEdit ie = {.start_byte = ed.pos,
                    .old_end_byte = ed.pos + ed.del,
                    .new_end_byte = ed.pos + inslen,
                    .start_point = point_at(text, ed.pos),
                    .old_end_point = point_at(text, ed.pos + ed.del),
                    .new_end_point = point_at(nt, ed.pos + inslen)};
  TSTree *edited = ts_tree_copy(old);
  ts_tree_edit(edited, &ie);
  TSTree *incr = ts_parser_parse_string(parser, edited, nt, nlen);
  TSTree *full = ts_parser_parse_string(parser, NULL, nt, nlen);
  SB a = {0}, b = {0};
  dump(ts_tree_root_node(incr), &a, 0);
  dump(ts_tree_root_node(full), &b, 0);
  int equal = a.len == b.len && !memcmp(a.buf, b.buf, a.len);
  n_edits++;
  if (!equal) {
    n_mismatch++;
    if (n_mismatch <= 200) {
      int no = (int)n_mismatch;
      write_file("mismatch", no, "incr.txt", a.buf, a.len);
      write_file("mismatch", no, "full.txt", b.buf, b.len);
      write_file("mismatch", no, "new.nix", nt, nlen);
      char meta[4600];
      int m = snprintf(meta, sizeof meta, "%s\n%s pos=%u del=%u ins=[%s]\n",
                       file, ed.kind, ed.pos, ed.del, ed.ins);
      write_file("mismatch", no, "meta", meta, m);
    }
    printf("MISMATCH %s %s pos=%u del=%u ins=[%s]\n", file, ed.kind, ed.pos,
           ed.del, !strcmp(ed.ins, "\n") ? "\\n" : ed.ins);
  }
  free(a.buf);
  free(b.buf);
  free(nt);
  ts_tree_delete(incr);
  ts_tree_delete(full);
  ts_tree_delete(edited);
}

// never split a UTF-8 sequence: advance to the next ASCII byte
static uint32_t ascii_pos(const char *t, uint32_t len, uint32_t p) {
  while (p < len && ((unsigned char)t[p] & 0x80))
    p++;
  return p;
}

static void run_file(TSParser *parser, const char *file, int npos) {
  FILE *f = fopen(file, "rb");
  if (!f) {
    fprintf(stderr, "skip %s: cannot open\n", file);
    return;
  }
  fseek(f, 0, SEEK_END);
  long len = ftell(f);
  fseek(f, 0, SEEK_SET);
  char *text = malloc(len + 1);
  size_t got = fread(text, 1, len, f);
  text[got] = 0;
  fclose(f);
  TSTree *old = ts_parser_parse_string(parser, NULL, text, got);
  static const char *inserts[] = {"''", "${", "/", "\"", "#",  "\n", "}", "{",
                                  " ",  "'",  "$", "\\", "/*", "*/", NULL};
  for (int i = 0; i < npos; i++) {
    uint32_t p = ascii_pos(text, got,
                           (uint32_t)(((uint64_t)(i + 1) * got) / (npos + 1)));
    run_edit(parser, file, text, got, old, (Edit){"insert", p, 0, "x"});
    run_edit(parser, file, text, got, old, (Edit){"delete", p, 1, ""});
    run_edit(parser, file, text, got, old, (Edit){"replace", p, 1, "x"});
    for (int k = 0; inserts[k]; k++)
      run_edit(parser, file, text, got, old, (Edit){"ins", p, 0, inserts[k]});
    run_edit(parser, file, text, got, old, (Edit){"del2", p, 2, ""});
  }
  ts_tree_delete(old);
  free(text);
}

int main(int argc, char **argv) {
  int npos = 10;
  long max_mismatch = 0;
  const char *list = NULL;
  const char *so = NULL;
  int first_file = argc;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--npos") && i + 1 < argc)
      npos = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--max-mismatches") && i + 1 < argc)
      max_mismatch = atol(argv[++i]);
    else if (!strcmp(argv[i], "--out") && i + 1 < argc)
      outdir = argv[++i];
    else if (!strcmp(argv[i], "--files") && i + 1 < argc)
      list = argv[++i];
    else if (!so)
      so = argv[i];
    else {
      first_file = i;
      break;
    }
  }
  if (!so) {
    fprintf(stderr, "usage: incr_harness [--npos N] [--max-mismatches M] "
                    "[--out DIR] [--files LIST] <lang.so> [file...]\n");
    return 2;
  }
  void *h = dlopen(so, RTLD_NOW);
  if (!h) {
    fprintf(stderr, "dlopen: %s\n", dlerror());
    return 2;
  }
  const TSLanguage *(*lf)(void) = dlsym(h, "tree_sitter_nix");
  if (!lf) {
    fprintf(stderr, "no tree_sitter_nix symbol in %s\n", so);
    return 2;
  }
  TSParser *parser = ts_parser_new();
  ts_parser_set_language(parser, lf());
  uint64_t n_files = 0;
  for (int i = first_file; i < argc; i++) {
    run_file(parser, argv[i], npos);
    n_files++;
  }
  if (list) {
    FILE *f = fopen(list, "r");
    if (!f) {
      perror(list);
      return 2;
    }
    char path[4096];
    while (fgets(path, sizeof path, f)) {
      path[strcspn(path, "\n")] = 0;
      if (*path) {
        run_file(parser, path, npos);
        n_files++;
      }
    }
    fclose(f);
  }
  ts_parser_delete(parser);
  char p[4096];
  snprintf(p, sizeof p, "%s/summary.json", outdir);
  FILE *s = fopen(p, "w");
  if (s) {
    fprintf(s,
            "{\"files\": %llu, \"npos\": %d, \"edits\": %llu, \"mismatches\": "
            "%llu}\n",
            (unsigned long long)n_files, npos, (unsigned long long)n_edits,
            (unsigned long long)n_mismatch);
    fclose(s);
  }
  printf("incremental: %llu files, %llu edits, %llu mismatches (allowed %ld)\n",
         (unsigned long long)n_files, (unsigned long long)n_edits,
         (unsigned long long)n_mismatch, max_mismatch);
  if ((long)n_mismatch > max_mismatch) {
    printf(
        "FAIL: incremental parse differs from fresh parse; see %s/mismatch-*\n",
        outdir);
    return 1;
  }
  printf("OK\n");
  return 0;
}
