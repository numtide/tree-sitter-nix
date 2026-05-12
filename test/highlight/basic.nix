{
  or = { or = 1; }.or or 42;
  # <- variable.member
  #  ^ operator
  #      ^ variable.member
  #                 ^ variable.member
  #                    ^ keyword.operator
  the-question = if builtins.true then "to be" else "not to be";
  # <- variable.member
  #  ^ variable.member
  #    ^ variable.member
  #               ^ keyword.conditional
  #                  ^ constant.builtin
  #                           ^ variable.member
  #                                ^ keyword.conditional
  #                                      ^ string
  #                                             ^ keyword.conditional
  #                                                    ^ string
  null = if null then true else false;
  # <- variable.member
  #          ^ constant.builtin
  #                    ^ boolean
  #                              ^ boolean
  pkgs' = { inherit (pkgs) stdenv lib; };
  # <- variable.member
  #   ^ variable.member
  #          ^ keyword
  #                   ^ variable
  #                         ^ variable.member
  #                                ^ variable.member
  thing' =
    # <- variable.member
    let inherit (pkgs) stdenv lib;
    # <- keyword
    #    ^ keyword
    #             ^ variable
    #                   ^ variable.member
    #                          ^ variable.member
    in derivation rec {
    # <- keyword
      # ^ function.builtin
      #            ^ keyword
      pname = "thing";
      # <- variable.member
      #         ^ string
      version = "v1.2.3";
      name = "${pname}-${version}";
      # <- variable.member
      #      ^ string
      #       ^ punctuation.special
      #          ^ variable
      #              ^ punctuation.special
      #               ^ string
      #                   ^ variable
      #                          ^ string
      buildInputs = with pkgs; [ thing_a thing_b ];
      # <- variable.member
      #              ^ keyword
      #                   ^ variable
      #                           ^ variable
      #                                    ^ variable
    };
  assert_bool = bool: assert lib.isBool bool; bool;
  # <- function
  #               ^ variable.parameter
  #                     ^ keyword
  #                            ^ variable
  #                                ^ function.call
  #                                       ^ variable
  #                                             ^ variable
  import = import ./overlays.nix { inherit pkgs; };
  # <- variable.member
  #         ^ keyword.import
  #                 ^ string.special.path
  #                                 ^ keyword
  #                                         ^ variable.member
  uri = https://github.com;
  #      ^ string.special.url
  #                ^ string.special.url
}
