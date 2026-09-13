#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
plugin_id=io.github.vitorpacheco.mega
config_root="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy"
target="$config_root/plugins/$plugin_id"
omarchy plugin validate "$source_dir"
mkdir -p "$config_root/plugins"
if [[ -e "$target" || -L "$target" ]]; then
  printf 'O destino já existe: %s\nAtualize os arquivos dessa instalação explicitamente.\n' "$target" >&2
  exit 1
fi
mkdir "$target"
cp "$source_dir/manifest.json" "$source_dir/Widget.qml" "$source_dir/Service.qml" "$source_dir/I18n.js" "$source_dir/README.md" "$source_dir/LICENSE" "$target/"
cp -R "$source_dir/bin" "$target/"
if [[ -f "$config_root/shell.json" ]]; then
  cp -p "$config_root/shell.json" "$config_root/shell.json.bak.mega.$(date +%s)"
fi
omarchy-shell shell rescanPlugins
omarchy plugin enable "$plugin_id"
printf 'Plugin instalado em %s\n' "$target"
if ! command -v mega-exec >/dev/null; then
  printf 'Instale o MEGAcmd e entre na conta pelo botão do painel. Consulte README.md.\n'
fi
