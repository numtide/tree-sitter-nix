(* End-to-end smoke test for the OCaml binding + runtime wrapper.
   Parses a small Nix snippet, walks the tree, extracts attribute names
   from the top-level attrset. Verifies the full Parser → Tree → Node
   pipeline works. *)

let src =
  {|
  {
    hello = "world";
    n = 42;
    nested = {
      deeper = true;
    };
  }
|}

(* Collect leaf identifier texts where the parent binding has an attrpath.
   This is the classic "extract top-level attrnames" traversal. *)
let collect_attrnames root ~src =
  let out = ref [] in
  let rec walk node =
    let ty = Tree_sitter_nix.Node.type_ node in
    if ty = "binding" then (
      (* binding -> attrpath -> identifier (leaf) *)
      for i = 0 to Tree_sitter_nix.Node.child_count node - 1 do
        let child = Tree_sitter_nix.Node.child node i in
        if Tree_sitter_nix.Node.type_ child = "attrpath" then
          Tree_sitter_nix.Node.iter_children child (fun leaf ->
              if Tree_sitter_nix.Node.type_ leaf = "identifier" then
                out := Tree_sitter_nix.Node.text leaf ~src :: !out)
      done);
    Tree_sitter_nix.Node.iter_named_children node walk
  in
  walk root;
  List.rev !out

let () =
  (* 1. Language pointer is non-null. *)
  let lang = Tree_sitter_nix.language () in
  if Obj.repr lang == Obj.repr () then
    failwith "language () returned null";

  (* 2. Parser + tree end-to-end. *)
  let parser = Tree_sitter_nix.Parser.create () in
  let tree = Tree_sitter_nix.Parser.parse_string parser src in
  let root = Tree_sitter_nix.Tree.root_node tree in
  let ty = Tree_sitter_nix.Node.type_ root in
  Printf.printf "root type: %s (named_children=%d, has_error=%b)\n" ty
    (Tree_sitter_nix.Node.named_child_count root)
    (Tree_sitter_nix.Node.has_error root);

  if Tree_sitter_nix.Node.has_error root then
    failwith "parse produced an ERROR node";

  (* 3. Walk tree and extract bindings' attribute names. *)
  let names = collect_attrnames root ~src in
  Printf.printf "attrnames: %s\n" (String.concat ", " names);

  let expected_subset = [ "hello"; "n"; "nested"; "deeper" ] in
  List.iter
    (fun want ->
      if not (List.mem want names) then
        failwith (Printf.sprintf "missing expected attrname: %s" want))
    expected_subset;

  print_endline "ok: parser, tree, node traversal all working"
