;; Mark arbitrary languages via a preceding comment. The comment body is
;; stripped of the surrounding `#` or `/* … */` delimiters with #gsub!
;; so e.g. `# bash`, `#bash`, `/* bash */` all resolve to `bash`.
((((comment) @injection.language) .
  (indented_string_expression (string_fragment) @injection.content))
  (#gsub! @injection.language "^#[[:space:]]*" "")
  (#gsub! @injection.language "^/\\*[[:space:]]*" "")
  (#gsub! @injection.language "[[:space:]]*\\*/$" "")
  (#set! injection.combined))

;; Common binding-name → bash injections.
;; Covers Phase/Hook/Script conventions used across nixpkgs stdenv.
((binding
   attrpath: (attrpath (identifier) @_path)
   expression: (indented_string_expression
     (string_fragment) @injection.content))
 (#match? @_path "(^\\w*Phase|(pre|post)\\w*|(.*\\.)?\\w*([sS]cript|[hH]ook)|(.*\\.)?startup)$")
 (#set! injection.language "bash")
 (#set! injection.combined))

;; pkgs.writeShellScript / writeShellScriptBin — 2nd argument is bash.
((apply_expression
   function: (apply_expression function: (_) @_func)
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_func "(^|\\.)writeShellScript(Bin)?$")
 (#set! injection.language "bash")
 (#set! injection.combined))

;; pkgs.runCommand variants — 3rd positional argument (command body) is bash.
(apply_expression
  (apply_expression
    function: (apply_expression
      function: ((_) @_func)))
    argument: (indented_string_expression (string_fragment) @injection.content)
  (#match? @_func "(^|\\.)runCommand(((No)?(CC))?(Local)?)?$")
  (#set! injection.language "bash")
  (#set! injection.combined))

;; pkgs.writeShellApplication — the `text` attribute is bash, whether
;; passed as a direct indented string or wrapped in `let … in "…"`.
(apply_expression
  function: ((_) @_func)
  argument: (_ (_)* (_ (_)* (binding
    attrpath: (attrpath (identifier) @_path)
     expression: (indented_string_expression
       (string_fragment) @injection.content))))
  (#match? @_func "(^|\\.)writeShellApplication$")
  (#match? @_path "^text$")
  (#set! injection.language "bash")
  (#set! injection.combined))

;; writeShellApplication with `text = let … in "…"` — follow the let body.
(apply_expression
  function: ((_) @_func)
  argument: (_ (_)* (_ (_)* (binding
    attrpath: (attrpath (identifier) @_path)
     expression: (let_expression
       body: (indented_string_expression
         (string_fragment) @injection.content)))))
  (#match? @_func "(^|\\.)writeShellApplication$")
  (#match? @_path "^text$")
  (#set! injection.language "bash")
  (#set! injection.combined))

;; lib.literalExpression / lib.literalExpressionPrefix — the string
;; argument is a Nix expression shown in docs; highlight as nix.
;; Uses specific node-type alternation rather than (_) to avoid
;; interference with other query captures.
((apply_expression
   function: [
     (variable_expression (identifier) @_func)
     (select_expression attrpath: (attrpath attr: (identifier) @_func .))
   ]
   argument: (indented_string_expression
     (string_fragment) @injection.content))
 (#match? @_func "^literalExpression(Prefix)?$")
 (#set! injection.language "nix")
 (#set! injection.combined))
((apply_expression
   function: [
     (variable_expression (identifier) @_func)
     (select_expression attrpath: (attrpath attr: (identifier) @_func .))
   ]
   argument: (string_expression
     (string_fragment) @injection.content))
 (#match? @_func "^literalExpression(Prefix)?$")
 (#set! injection.language "nix"))

;; nixos testScript binding — value is Python.
((binding
   attrpath: (attrpath (identifier) @_path)
   expression: (indented_string_expression
     (string_fragment) @injection.content))
 (#eq? @_path "testScript")
 (#set! injection.language "python")
 (#set! injection.combined))
((binding
   attrpath: (attrpath (identifier) @_path)
   expression: (let_expression
     body: (indented_string_expression
       (string_fragment) @injection.content)))
 (#eq? @_path "testScript")
 (#set! injection.language "python")
 (#set! injection.combined))

;; ----------------------------------------------------------------------
;; Filename-based injection for indented strings.
;;
;; Detect the language from the file extension of a preceding filename
;; argument in any curried call:
;;
;;   pkgs.writeText "index.html" ''
;;     <div>Hello</div>
;;   ''
;;   pkgs.writeShellScriptBin "run.sh" ''
;;     echo hi
;;   ''
;;
;; The pattern matches any `f "name.ext" '' ... ''` shape. False
;; positives (a curried call with a filename-shaped argument that isn't
;; a file writer) are tolerated — the worst case is mis-highlighting,
;; whereas false negatives mean no highlighting at all.
;;
;; Concept harvested from nix-community/tree-sitter-nix#169 by
;; @nuketownada; rewritten as a hand-maintained list rather than
;; generated from a Nix derivation.

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(sh|bash)$")
 (#set! injection.language "bash")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(py)$")
 (#set! injection.language "python")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(html|htm)$")
 (#set! injection.language "html")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(css)$")
 (#set! injection.language "css")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(js|mjs|cjs)$")
 (#set! injection.language "javascript")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(ts|mts|cts)$")
 (#set! injection.language "typescript")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(json)$")
 (#set! injection.language "json")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(yml|yaml)$")
 (#set! injection.language "yaml")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(toml)$")
 (#set! injection.language "toml")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(lua)$")
 (#set! injection.language "lua")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(nix)$")
 (#set! injection.language "nix")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(xml)$")
 (#set! injection.language "xml")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(md)$")
 (#set! injection.language "markdown")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(sql)$")
 (#set! injection.language "sql")
 (#set! injection.combined))

((apply_expression
   function: (apply_expression
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression (string_fragment) @injection.content))
 (#match? @_filename "\\.(conf|ini)$")
 (#set! injection.language "ini")
 (#set! injection.combined))
