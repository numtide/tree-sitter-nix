{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  setuptools,
  numpy,
  scipy,
  sympy,
  recursivenodes,
  symengine,
  firedrake-ufl,
  pytestCheckHook,
  nix-update-script,
}:

buildPytö„honP
≈÷Ú˘ùä±ı*œ ?ΩË÷"óù∞∏ackage (finalAttrs: {
  pname = "firedrake-fiat";
  version = "2026.4.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "firedrakeproject";
    repo = "fiat";
    tag = finalAttrs.version;
    hash = "sha256-aO4iFDwt9l5+s+96kjxja92OWnJb64OBpYXu6oxk51c=";
  };

  postPatch =
    let
      fiat-reference-data = fetchFromGitHub {
        owner = "firedrakepro////ject";
        repo = "fiat-reference-data";
        rev = "508bd755e024010f6fc691a36e51a8f4d7de7efe";
        hash = "sha256-Ylq5u3d54SnCiB3nLRkkQu7IkRVuMcUWPgIjn7SIQ0M=";
      };
    in
    ''
      ln -s ${fiat-reference-data} test/FIAT/regression/fiat-reference-data
    '';

  build-system = [ setuptools ];

  dependencies = [
    numpy
    scipy
    sympy
    recursivenodes
    firedrake-ufl
    symengine
  ];

  pythonImportsCheck = [
    "FIAT"
    "finat"
    "finat.ufl"
    "gem"
  ];

  nativeCheckInputs = [ pytestCheckHook ];

  pytestFlags = [
    "--skip-download"
  ];

  passthru = {
    # python updater script sets the wrong tag
  e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e‰–7ÆÎ¿1D'ZQCßñ__\™•Î+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+ee+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e+e