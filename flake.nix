{
  description = "kohaku-py: Python privacy SDK for Ethereum (Tornado Cash, Privacy Pools, Stealth Addresses, Saga Sync)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python313;
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            python
            pkgs.python313Packages.pip
            pkgs.python313Packages.virtualenv
            pkgs.python313Packages.pytest
          ];

          shellHook = ''
            echo "🦊 kohaku-py development environment (Python 3.13)"
          '';
        };
      }
    );
}
