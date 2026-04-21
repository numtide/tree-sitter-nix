(* Smoke test: the language pointer must be non-null. *)

let () =
  let lang = Tree_sitter_nix.language () in
  if Obj.repr lang == Obj.repr () then
    failwith "tree_sitter_nix.language () returned null"
  else
    print_endline "ok: tree_sitter_nix.language () returned a non-null pointer"
