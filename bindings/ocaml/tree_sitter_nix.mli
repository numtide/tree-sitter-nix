(** OCaml bindings for the tree-sitter-nix grammar.

    This library exposes the compiled Nix parser as an opaque [TSLanguage]
    pointer usable with any tree-sitter runtime that accepts a
    [TSLanguage *], such as {{:https://github.com/semgrep/ocaml-tree-sitter-core}
    ocaml-tree-sitter-core}.

    Example (with ocaml-tree-sitter-core):
    {[
      let lang = Tree_sitter_nix.language () in
      let tree = Tree_sitter.Parser.parse_string ~language:lang "{ a = 1; }" in
      ...
    ]}
*)

(** [language ()] returns an opaque pointer to the Nix [TSLanguage].

    The return value is a boxed C pointer; it is opaque to OCaml but safe to
    pass to C functions expecting a [const TSLanguage *]. The pointer has
    static lifetime (owned by the linked shared object), so it must not be
    freed by the caller. *)
val language : unit -> Obj.t
