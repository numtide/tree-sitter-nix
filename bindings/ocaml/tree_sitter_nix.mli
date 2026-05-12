(** OCaml bindings for the tree-sitter-nix grammar.

    This library bundles:
    - The compiled Nix grammar (parser.c, scanner.c).
    - A minimal wrapper around libtree-sitter's C runtime, so consumers
      can parse Nix source and walk the resulting tree without pulling
      in ocaml-tree-sitter-core.

    Usage:
    {[
      let parser = Tree_sitter_nix.Parser.create () in
      let tree = Tree_sitter_nix.Parser.parse_string parser "{ a = 1; }" in
      let root = Tree_sitter_nix.Tree.root_node tree in
      Printf.printf "root type: %s\n" (Tree_sitter_nix.Node.type_ root)
    ]} *)

(** Opaque pointer to the grammar's [TSLanguage]. Pass this to
    {!Parser.set_language} (done automatically by {!Parser.create}).

    [language ()] returns the same static pointer every call; no need
    to cache it. Kept for ABI-level interop with other tooling that
    wants a raw [TSLanguage *]. *)
val language : unit -> Obj.t

module Node : sig
  (** A handle to a node in a parsed tree. Nodes are value-types (the
      underlying [TSNode] is 32 bytes of context); comparing two nodes
      with [=] does NOT compare the nodes they point to. *)
  type t

  (** The node's grammar type name, e.g. ["attrset_expression"]. *)
  val type_ : t -> string

  (** [true] if the node is the null sentinel (e.g. returned from
      [parent] at the root). *)
  val is_null : t -> bool

  (** [true] if the node is "named" (a grammar-level node, not an
      anonymous punctuation token like [";"] or ["{"]). *)
  val is_named : t -> bool

  (** [true] if this node or any descendant is an error node. *)
  val has_error : t -> bool

  (** Byte offset (0-based) of the start of this node in the source. *)
  val start_byte : t -> int

  (** Byte offset (0-based, exclusive) of the end of this node. *)
  val end_byte : t -> int

  (** Substring of the source corresponding to this node. *)
  val text : t -> src:string -> string

  (** Total number of children (named + anonymous). *)
  val child_count : t -> int

  (** [child n i] — [i]th child (0-indexed), including anonymous
      punctuation. *)
  val child : t -> int -> t

  (** Number of named children only. *)
  val named_child_count : t -> int

  (** [named_child n i] — [i]th named child. *)
  val named_child : t -> int -> t

  (** Parent node, or a null sentinel when called on the root. *)
  val parent : t -> t

  (** Grammar field name for the [i]th child, if any. *)
  val field_name_for_child : t -> int -> string option

  (** Iterate over all children (named + anonymous). *)
  val iter_children : t -> (t -> unit) -> unit

  (** Iterate over named children only. *)
  val iter_named_children : t -> (t -> unit) -> unit
end

module Tree : sig
  (** A parsed syntax tree. Freed automatically by the GC. *)
  type t

  (** Get the root node of the tree. *)
  val root_node : t -> Node.t
end

module Parser : sig
  (** A parser handle. The underlying [TSParser] is freed automatically
      when this value is garbage-collected. *)
  type t

  (** Create a new parser with the Nix language pre-loaded. *)
  val create : unit -> t

  (** Parse a UTF-8 source string. Never raises for well-formed UTF-8;
      parse errors are reflected as [ERROR] nodes in the resulting tree
      (check with {!Node.has_error}). *)
  val parse_string : t -> string -> Tree.t
end
