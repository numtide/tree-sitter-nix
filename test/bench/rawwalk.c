// Walk the raw Subtree structure (hidden nodes included) to attribute tree
// memory. Needs libtree-sitter's private headers (lib/src), so it only builds
// against a source checkout (TREE_SITTER_SRC), never against pkg-config.
//
// usage: rawwalk <lang.so> <file.nix | list.txt>
#define _GNU_SOURCE
#include "language.h"
#include "subtree.h"
#include "tree.h"
#include "tree_sitter/api.h"
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  uint64_t inline_leaf, heap_leaf, heap_internal, hidden_internal,
      visible_internal, heap_bytes, ext_leaf, extra_flag;
  uint64_t *per_sym_hidden;
} R;

static void walk(Subtree s, R *r) {
  if (s.data.is_inline) {
    r->inline_leaf++;
    return;
  }
  const SubtreeHeapData *d = s.ptr;
  r->heap_bytes += ts_subtree_alloc_size(d->child_count);
  if (d->extra)
    r->extra_flag++;
  if (d->child_count == 0) {
    r->heap_leaf++;
    if (d->has_external_tokens)
      r->ext_leaf++;
    return;
  }
  r->heap_internal++;
  if (d->visible)
    r->visible_internal++;
  else {
    r->hidden_internal++;
    r->per_sym_hidden[d->symbol]++;
  }
  const Subtree *ch = ts_subtree_children(s);
  for (uint32_t i = 0; i < d->child_count; i++)
    walk(ch[i], r);
}

int main(int argc, char **argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: %s <lang.so> <file.nix | list.txt>\n", argv[0]);
    return 2;
  }
  void *h = dlopen(argv[1], RTLD_NOW);
  if (!h) {
    fprintf(stderr, "dlopen: %s\n", dlerror());
    return 2;
  }
  const TSLanguage *(*fn)(void) = dlsym(h, "tree_sitter_nix");
  if (!fn) {
    fprintf(stderr, "no tree_sitter_nix symbol in %s\n", argv[1]);
    return 2;
  }
  const TSLanguage *lang = fn();
  TSParser *p = ts_parser_new();
  ts_parser_set_language(p, lang);
  R r = {0};
  r.per_sym_hidden = calloc(ts_language_symbol_count(lang), 8);
  long n = 0;
  size_t L = strlen(argv[2]);
  int islist = L > 4 && !strcmp(argv[2] + L - 4, ".txt");
  FILE *lf = islist ? fopen(argv[2], "r") : NULL;
  char path[4096];
  if (islist && !lf) {
    perror(argv[2]);
    return 2;
  }
  while (1) {
    const char *fp = argv[2];
    if (islist) {
      if (!fgets(path, sizeof path, lf))
        break;
      path[strcspn(path, "\n")] = 0;
      fp = path;
    }
    FILE *f = fopen(fp, "rb");
    if (!f) {
      if (!islist)
        break;
      continue;
    }
    fseek(f, 0, SEEK_END);
    long m = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *src = malloc(m + 1);
    size_t got = fread(src, 1, m, f);
    fclose(f);
    n += got;
    TSTree *t = ts_parser_parse_string(p, NULL, src, got);
    walk(t->root, &r);
    ts_tree_delete(t);
    free(src);
    if (!islist)
      break;
  }
  printf("input=%s bytes=%ld sizeof(SubtreeHeapData)=%zu sizeof(Subtree)=%zu\n",
         argv[2], n, sizeof(SubtreeHeapData), sizeof(Subtree));
  printf("inline_leaf=%llu heap_leaf=%llu (external=%llu) heap_internal=%llu "
         "visible_internal=%llu hidden_internal=%llu extra_flagged=%llu "
         "heap_bytes=%llu\n",
         (unsigned long long)r.inline_leaf, (unsigned long long)r.heap_leaf,
         (unsigned long long)r.ext_leaf, (unsigned long long)r.heap_internal,
         (unsigned long long)r.visible_internal,
         (unsigned long long)r.hidden_internal,
         (unsigned long long)r.extra_flag, (unsigned long long)r.heap_bytes);
  for (uint32_t i = 0; i < ts_language_symbol_count(lang); i++)
    if (r.per_sym_hidden[i])
      printf("hidden\t%s\t%llu\n", ts_language_symbol_name(lang, i),
             (unsigned long long)r.per_sym_hidden[i]);
  ts_parser_delete(p);
  return 0;
}
