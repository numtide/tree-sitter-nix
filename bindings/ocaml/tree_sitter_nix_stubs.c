/* OCaml C stubs for tree-sitter-nix.
 *
 * Exposes the generated `tree_sitter_nix()` function (declared in
 * `bindings/c/tree_sitter/tree-sitter-nix.h`) to OCaml as an opaque boxed
 * pointer. Callers can pass the result to any C function that expects a
 * `const TSLanguage *`.
 */

#include <caml/alloc.h>
#include <caml/memory.h>
#include <caml/mlvalues.h>

typedef struct TSLanguage TSLanguage;

extern const TSLanguage *tree_sitter_nix(void);

CAMLprim value caml_tree_sitter_nix_language(value unit) {
  CAMLparam1(unit);
  /* TSLanguage pointers are static; safe to cast and box. */
  CAMLreturn((value)tree_sitter_nix());
}
