/* OCaml C stubs for tree-sitter-nix.
 *
 * Exposes:
 *   - tree_sitter_nix() as the grammar's TSLanguage pointer.
 *   - A minimal subset of libtree-sitter's runtime (TSParser, TSTree,
 *     TSNode) as OCaml custom blocks + primitives.
 *
 * Consumers don't need ocaml-tree-sitter-core; they can parse Nix and
 * walk the resulting tree purely through this binding.
 */

#include <caml/alloc.h>
#include <caml/callback.h>
#include <caml/custom.h>
#include <caml/fail.h>
#include <caml/memory.h>
#include <caml/mlvalues.h>

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <tree_sitter/api.h>

extern const TSLanguage *tree_sitter_nix(void);

/* --------------------------------------------------------------------
 * Language
 * -------------------------------------------------------------------- */

CAMLprim value caml_tree_sitter_nix_language(value unit) {
  CAMLparam1(unit);
  /* TSLanguage pointers are static; safe to cast and box. */
  CAMLreturn((value)tree_sitter_nix());
}

/* --------------------------------------------------------------------
 * TSParser — custom block owning a parser instance
 * -------------------------------------------------------------------- */

#define Parser_val(v) (*((TSParser **)Data_custom_val(v)))

static void finalize_parser(value v) {
  TSParser *p = Parser_val(v);
  if (p)
    ts_parser_delete(p);
}

static struct custom_operations parser_ops = {
    "com.numtide.tree_sitter_nix.Parser",
    finalize_parser,
    custom_compare_default,
    custom_hash_default,
    custom_serialize_default,
    custom_deserialize_default,
    custom_compare_ext_default,
    custom_fixed_length_default,
};

static value alloc_parser(TSParser *p) {
  value v = caml_alloc_custom(&parser_ops, sizeof(TSParser *), 0, 1);
  Parser_val(v) = p;
  return v;
}

CAMLprim value caml_ts_parser_new(value unit) {
  CAMLparam1(unit);
  TSParser *p = ts_parser_new();
  if (!p)
    caml_failwith("ts_parser_new returned NULL");
  CAMLreturn(alloc_parser(p));
}

CAMLprim value caml_ts_parser_set_language(value parser_v, value lang_v) {
  CAMLparam2(parser_v, lang_v);
  TSParser *p = Parser_val(parser_v);
  const TSLanguage *lang = (const TSLanguage *)lang_v;
  bool ok = ts_parser_set_language(p, lang);
  if (!ok)
    caml_failwith("ts_parser_set_language failed (ABI mismatch?)");
  CAMLreturn(Val_unit);
}

/* --------------------------------------------------------------------
 * TSTree — custom block owning a parsed tree
 * -------------------------------------------------------------------- */

#define Tree_val(v) (*((TSTree **)Data_custom_val(v)))

static void finalize_tree(value v) {
  TSTree *t = Tree_val(v);
  if (t)
    ts_tree_delete(t);
}

static struct custom_operations tree_ops = {
    "com.numtide.tree_sitter_nix.Tree",
    finalize_tree,
    custom_compare_default,
    custom_hash_default,
    custom_serialize_default,
    custom_deserialize_default,
    custom_compare_ext_default,
    custom_fixed_length_default,
};

static value alloc_tree(TSTree *t) {
  value v = caml_alloc_custom(&tree_ops, sizeof(TSTree *), 0, 1);
  Tree_val(v) = t;
  return v;
}

CAMLprim value caml_ts_parser_parse_string(value parser_v, value src_v) {
  CAMLparam2(parser_v, src_v);
  CAMLlocal1(result);
  TSParser *p = Parser_val(parser_v);
  const char *src = String_val(src_v);
  mlsize_t len = caml_string_length(src_v);
  TSTree *tree = ts_parser_parse_string(p, NULL, src, (uint32_t)len);
  if (!tree)
    caml_failwith("ts_parser_parse_string returned NULL");
  result = alloc_tree(tree);
  CAMLreturn(result);
}

/* --------------------------------------------------------------------
 * TSNode — custom block holding a 32-byte value-type node handle.
 * -------------------------------------------------------------------- */

#define Node_val(v) ((TSNode *)Data_custom_val(v))

static struct custom_operations node_ops = {
    "com.numtide.tree_sitter_nix.Node",
    custom_finalize_default,
    custom_compare_default,
    custom_hash_default,
    custom_serialize_default,
    custom_deserialize_default,
    custom_compare_ext_default,
    custom_fixed_length_default,
};

static value alloc_node(TSNode n) {
  value v = caml_alloc_custom(&node_ops, sizeof(TSNode), 0, 1);
  memcpy(Data_custom_val(v), &n, sizeof(TSNode));
  return v;
}

CAMLprim value caml_ts_tree_root_node(value tree_v) {
  CAMLparam1(tree_v);
  TSTree *t = Tree_val(tree_v);
  TSNode n = ts_tree_root_node(t);
  CAMLreturn(alloc_node(n));
}

CAMLprim value caml_ts_node_type(value node_v) {
  CAMLparam1(node_v);
  const char *t = ts_node_type(*Node_val(node_v));
  CAMLreturn(caml_copy_string(t ? t : ""));
}

CAMLprim value caml_ts_node_start_byte(value node_v) {
  CAMLparam1(node_v);
  CAMLreturn(Val_int((intnat)ts_node_start_byte(*Node_val(node_v))));
}

CAMLprim value caml_ts_node_end_byte(value node_v) {
  CAMLparam1(node_v);
  CAMLreturn(Val_int((intnat)ts_node_end_byte(*Node_val(node_v))));
}

CAMLprim value caml_ts_node_is_null(value node_v) {
  CAMLparam1(node_v);
  CAMLreturn(Val_bool(ts_node_is_null(*Node_val(node_v))));
}

CAMLprim value caml_ts_node_is_named(value node_v) {
  CAMLparam1(node_v);
  CAMLreturn(Val_bool(ts_node_is_named(*Node_val(node_v))));
}

CAMLprim value caml_ts_node_has_error(value node_v) {
  CAMLparam1(node_v);
  CAMLreturn(Val_bool(ts_node_has_error(*Node_val(node_v))));
}

CAMLprim value caml_ts_node_child_count(value node_v) {
  CAMLparam1(node_v);
  CAMLreturn(Val_int((intnat)ts_node_child_count(*Node_val(node_v))));
}

CAMLprim value caml_ts_node_child(value node_v, value idx_v) {
  CAMLparam2(node_v, idx_v);
  TSNode child = ts_node_child(*Node_val(node_v), (uint32_t)Int_val(idx_v));
  CAMLreturn(alloc_node(child));
}

CAMLprim value caml_ts_node_named_child_count(value node_v) {
  CAMLparam1(node_v);
  CAMLreturn(Val_int((intnat)ts_node_named_child_count(*Node_val(node_v))));
}

CAMLprim value caml_ts_node_named_child(value node_v, value idx_v) {
  CAMLparam2(node_v, idx_v);
  TSNode child =
      ts_node_named_child(*Node_val(node_v), (uint32_t)Int_val(idx_v));
  CAMLreturn(alloc_node(child));
}

CAMLprim value caml_ts_node_parent(value node_v) {
  CAMLparam1(node_v);
  TSNode parent = ts_node_parent(*Node_val(node_v));
  CAMLreturn(alloc_node(parent));
}

CAMLprim value caml_ts_node_field_name_for_child(value node_v, value idx_v) {
  CAMLparam2(node_v, idx_v);
  CAMLlocal1(result);
  const char *name = ts_node_field_name_for_child(*Node_val(node_v),
                                                  (uint32_t)Int_val(idx_v));
  if (!name) {
    result = Val_int(0); /* None */
  } else {
    result = caml_alloc(1, 0); /* Some v */
    Store_field(result, 0, caml_copy_string(name));
  }
  CAMLreturn(result);
}
