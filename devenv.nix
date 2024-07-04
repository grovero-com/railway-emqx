{ pkgs, lib, config, inputs, ... }: let
  python = pkgs.python311;
  pypkgs = python.pkgs;
in {

  languages.python = {
    enable = true;
    package = python;
  };

  packages = [
    pkgs.git
    pkgs.mqttui
    pypkgs.typer
    pypkgs.paho-mqtt
    pypkgs.rich
    pypkgs.typed-settings
    pypkgs.pydantic

    pypkgs.python-lsp-server
    pypkgs.python-lsp-ruff
    pypkgs.pylsp-rope
    pypkgs.psycopg2
    pkgs.ruff
    pypkgs.rope

    pkgs.pgcli
  ];

  enterShell = ''
  '';

  # https://devenv.sh/tests/
  enterTest = ''
    echo "Running tests"
  '';

  # https://devenv.sh/services/
  services.postgres = {
    enable = true;
    listen_addresses = "127.0.0.1";
    initialDatabases = [
      { name = "mqtt"; schema = ./mqtt-schema.sql; }
    ];
  };

  # https://devenv.sh/languages/
  # languages.nix.enable = true;

  # https://devenv.sh/pre-commit-hooks/
  # pre-commit.hooks.shellcheck.enable = true;

  # https://devenv.sh/processes/
  # processes.ping.exec = "ping example.com";

  # See full reference at https://devenv.sh/reference/options/
}
