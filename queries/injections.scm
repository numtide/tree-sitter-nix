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

;; pkgs.writeText / writeTextFile / writeTextDir — use the filename
;; argument's extension to pick a language.
((apply_expression
   function: (apply_expression
     function: (variable_expression (identifier) @_func)
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression
     (string_fragment) @injection.content))
 (#match? @_func "^writeText(File|Dir)?$")
 (#match? @_filename "\\.sh$")
 (#set! injection.language "bash")
 (#set! injection.combined))
((apply_expression
   function: (apply_expression
     function: (variable_expression (identifier) @_func)
     argument: (string_expression (string_fragment) @_filename))
   argument: (indented_string_expression
     (string_fragment) @injection.content))
 (#match? @_func "^writeText(File|Dir)?$")
 (#match? @_filename "\\.py$")
 (#set! injection.language "python")
 (#set! injection.combined))
