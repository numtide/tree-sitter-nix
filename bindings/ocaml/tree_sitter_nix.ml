(** Implementation — see tree_sitter_nix.mli for the public API. *)

external tree_sitter_nix_language_stub : unit -> Obj.t
  = "caml_tree_sitter_nix_language"

let language () = tree_sitter_nix_language_stub ()

module Node = struct
  type t

  external type_ : t -> string = "caml_ts_node_type"
  external is_null : t -> bool = "caml_ts_node_is_null"
  external is_named : t -> bool = "caml_ts_node_is_named"
  external has_error : t -> bool = "caml_ts_node_has_error"
  external start_byte : t -> int = "caml_ts_node_start_byte"
  external end_byte : t -> int = "caml_ts_node_end_byte"
  external child_count : t -> int = "caml_ts_node_child_count"
  external child : t -> int -> t = "caml_ts_node_child"
  external named_child_count : t -> int = "caml_ts_node_named_child_count"
  external named_child : t -> int -> t = "caml_ts_node_named_child"
  external parent : t -> t = "caml_ts_node_parent"

  external field_name_for_child : t -> int -> string option
    = "caml_ts_node_field_name_for_child"

  let text n ~src =
    let s = start_byte n and e = end_byte n in
    let clamped_e = min e (String.length src) in
    if s >= clamped_e then "" else String.sub src s (clamped_e - s)

  let iter_children n f =
    for i = 0 to child_count n - 1 do
      f (child n i)
    done

  let iter_named_children n f =
    for i = 0 to named_child_count n - 1 do
      f (named_child n i)
    done
end

module Tree = struct
  type t

  external root_node : t -> Node.t = "caml_ts_tree_root_node"
end

module Parser = struct
  type t

  external create_raw : unit -> t = "caml_ts_parser_new"
  external set_language : t -> Obj.t -> unit = "caml_ts_parser_set_language"
  external parse_string : t -> string -> Tree.t = "caml_ts_parser_parse_string"

  let create () =
    let p = create_raw () in
    set_language p (language ());
    p
end
