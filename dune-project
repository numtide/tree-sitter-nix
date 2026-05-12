(lang dune 3.0)

(name tree_sitter_nix)

(generate_opam_files true)

(source
 (github numtide/tree-sitter-nix))

(license MIT)

(authors "Charles Strahan <charles@cstrahan.com>" "numtide contributors")

(maintainers "numtide <contact@numtide.com>")

(package
 (name tree_sitter_nix)
 (synopsis "Tree-sitter grammar for Nix")
 (description
  "OCaml bindings for the tree-sitter-nix grammar. Exposes the compiled Nix parser as a TSLanguage for use with a tree-sitter runtime such as ocaml-tree-sitter-core.")
 (depends
  (ocaml
   (>= 4.14))
  (dune
   (>= 3.0))
  (dune-configurator
   (>= 3.0)))
 (tags
  ("tree-sitter" "nix" "parsing" "grammar")))
