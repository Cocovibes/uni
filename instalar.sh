#!/usr/bin/env bash
# Instala el sistema de estudio en esta máquina.
# Idempotente: se puede volver a ejecutar sin romper nada.
#
#   ./instalar.sh              todo
#   ./instalar.sh plugins      solo los plugins de Obsidian
#
# No usa sudo en ningún momento.

set -euo pipefail

VAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || true)"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
info() { printf '  \033[2m·\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
head_() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ─────────────────────────── requisitos ────────────────────────────
requisitos() {
  head_ "Requisitos"
  [ -n "$PY" ] || { echo "Falta python3."; exit 1; }
  ok "python3 → $PY ($("$PY" -V 2>&1))"

  if "$PY" -c 'import yaml' 2>/dev/null; then
    ok "PyYAML"
  else
    info "PyYAML no está; instalando para el usuario…"
    "$PY" -m pip install --user --quiet pyyaml \
      || { warn "No se pudo instalar PyYAML."
           warn "En Fedora: sudo dnf install python3-pyyaml"
           warn "En Debian/Ubuntu: sudo apt install python3-yaml"; exit 1; }
    ok "PyYAML instalado"
  fi
}

# ──────────────────── plugins de Obsidian ──────────────────────────
# id|repo canónico|versión fijada|assets
# El repo sale del registro oficial (github.com/obsidianmd/obsidian-releases,
# community-plugins.json). Tras bajarlo se comprueba que el id del manifest
# coincide con el esperado: así se detecta que una release esté publicada bajo
# otro id (le pasa a Calendar, cuya "latest" es una beta con id calendar-beta).
PLUGINS=(
  "dataview|blacksmithgu/obsidian-dataview|0.5.68|main.js manifest.json styles.css"
  "obsidian-tasks-plugin|obsidian-tasks-group/obsidian-tasks|8.3.0|main.js manifest.json styles.css"
  "calendar|liamcain/obsidian-calendar-plugin|1.5.10|main.js manifest.json"
)

plugins() {
  head_ "Plugins de Obsidian (descarga verificada)"
  command -v curl >/dev/null || { warn "Falta curl; me salto los plugins."; return 0; }

  for linea in "${PLUGINS[@]}"; do
    IFS='|' read -r id repo ver assets <<<"$linea"
    destino="$VAULT/.obsidian/plugins/$id"

    if [ -f "$destino/manifest.json" ] &&
       [ "$("$PY" -c "import json;print(json.load(open('$destino/manifest.json'))['version'])" 2>/dev/null)" = "$ver" ]; then
      ok "$id $ver (ya estaba)"
      continue
    fi

    tmp="$(mktemp -d)"
    for a in $assets; do
      curl -fsSL -o "$tmp/$a" \
        "https://github.com/$repo/releases/download/$ver/$a" \
        || { warn "$id: no se pudo bajar $a"; rm -rf "$tmp"; continue 2; }
    done

    real="$("$PY" -c "import json;print(json.load(open('$tmp/manifest.json'))['id'])")"
    if [ "$real" != "$id" ]; then
      warn "$id: el manifest dice id='$real'. Release equivocada, no lo instalo."
      rm -rf "$tmp"; continue
    fi

    mkdir -p "$destino"
    for a in $assets; do cp "$tmp/$a" "$destino/$a"; done
    rm -rf "$tmp"
    ok "$id $ver ← $repo (id verificado)"
  done

  # Obsidian solo carga los que estén en esta lista.
  "$PY" - "$VAULT" <<'EOF'
import json, pathlib, sys
f = pathlib.Path(sys.argv[1], ".obsidian", "community-plugins.json")
quiere = ["dataview", "obsidian-tasks-plugin", "calendar"]
hay = [p for p in quiere if (f.parent / "plugins" / p / "main.js").exists()]
f.write_text(json.dumps(hay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"  \033[32m✓\033[0m activados: {', '.join(hay) or '(ninguno)'}")
EOF

  if command -v flatpak >/dev/null && flatpak info md.obsidian.Obsidian >/dev/null 2>&1; then
    flatpak override --user --filesystem="$VAULT" md.obsidian.Obsidian \
      && ok "flatpak: acceso a $VAULT concedido"
    info "el flatpak de Obsidian NO ve tu \$HOME por defecto; sin esto el vault no abre"
  fi
}

# ───────────────────────── comando `uni` ───────────────────────────
comando() {
  head_ "Comando uni"
  mkdir -p "$HOME/.local/bin"
  sed "s|@VAULT@|$VAULT|g" "$VAULT/sistema/uni" > "$HOME/.local/bin/uni"
  chmod +x "$HOME/.local/bin/uni"
  ok "$HOME/.local/bin/uni"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) warn "~/.local/bin no está en el PATH; añádelo a tu shell" ;;
  esac
}

# ──────────────────── aviso diario (systemd) ───────────────────────
aviso() {
  head_ "Aviso diario 08:30"
  command -v systemctl >/dev/null || { warn "Sin systemd; me lo salto."; return 0; }
  d="$HOME/.config/systemd/user"; mkdir -p "$d"
  sed -e "s|@VAULT@|$VAULT|g" -e "s|@PY@|$PY|g" \
      "$VAULT/sistema/uni-hoy.service" > "$d/uni-hoy.service"
  cp "$VAULT/sistema/uni-hoy.timer" "$d/uni-hoy.timer"
  systemctl --user daemon-reload
  systemctl --user enable --now uni-hoy.timer
  ok "uni-hoy.timer activo — $(systemctl --user list-timers uni-hoy.timer --no-legend | awk '{print $1, $2, $3}')"
  info "pararlo: systemctl --user disable --now uni-hoy.timer"
}

# ─────────────── calendario del sistema (GNOME/EDS) ────────────────
calendario() {
  head_ "Calendario del sistema"
  if ! command -v gnome-calendar >/dev/null && [ ! -d "$HOME/.config/evolution" ]; then
    info "no veo GNOME Calendar / Evolution; me lo salto"
    info "el .ics igualmente se genera en out/ y lo abre cualquier calendario"
    return 0
  fi
  d="$HOME/.config/evolution/sources"; mkdir -p "$d"
  sed "s|@VAULT@|$VAULT|g" "$VAULT/sistema/uni-estudio.source" > "$d/uni-estudio.source"
  ok "fuente EDS → enlace en vivo a out/uni-estudio.ics"
  pkill -f '[e]volution-calendar-factory' 2>/dev/null || true
  info "si no aparece, cierra y abre GNOME Calendar una vez"
}

# ───────────────────────────── main ────────────────────────────────
case "${1:-todo}" in
  plugins) requisitos; plugins ;;
  todo)
    requisitos; plugins; comando; aviso; calendario
    head_ "Primer sync"
    mkdir -p "$VAULT/Exámenes" "$VAULT/Asignaturas"
    "$PY" "$VAULT/uni.py" sync
    printf '\n\033[1mListo.\033[0m Abre el vault %s en Obsidian y verás el Panel.\n' "$VAULT"
    printf 'Examen nuevo → nota en Exámenes/ con la plantilla, y `uni sync`.\n\n'
    ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
