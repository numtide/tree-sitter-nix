{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  packages = [
    pkgs.nodejs
    pkgs.python3

    pkgs.tree-sitter
    pkgs.editorconfig-checker

    pkgs.rustc
    pkgs.cargo

    # Formatters
    pkgs.treefmt
    pkgs.nixpkgs-fmt
    pkgs.prettier
    pkgs.rustfmt
    pkgs.clang-tools
  ];

  # The C harnesses (make memory/incremental/fuzz-asan) compile
  # libtree-sitter from source; point them at nixpkgs' copy instead of
  # downloading a tarball inside the shell.
  shellHook = ''
    export TREE_SITTER_SRC=${pkgs.tree-sitter.src}
  '';
}
