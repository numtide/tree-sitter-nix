(** See [tree_sitter_nix.mli] for the public interface documentation. *)

external tree_sitter_nix_stub : unit -> Obj.t = "caml_tree_sitter_nix_language"

let language () = tree_sitter_nix_stub ()
