#!/usr/bin/env bash
# Claude-Code-Hook: haelt dieses Repo automatisch mit GitHub synchron.
# Plattformunabhaengig (nur bash + git) - laeuft am PC (Git Bash) und in Linux-Cloud-Sitzungen.
#   git-sync.sh pull  -> SessionStart: neuesten Stand holen
#   git-sync.sh push  -> Stop: Aenderungen committen und pushen
# Fehler (offline, Konflikt) blockieren die Sitzung nie: immer exit 0, nur kurze Meldung.

mode="$1"
dir="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$dir" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

export GIT_TERMINAL_PROMPT=0   # nie auf eine Passwort-Eingabe warten
say() { printf '{"systemMessage": "git-sync: %s"}\n' "$1"; }

in_rebase() { [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; }
has_upstream() { git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; }

pull() {
  if has_upstream; then
    git pull --rebase --autostash -q >/dev/null 2>&1
  else
    # z.B. frischer claude/*-Branch in der Cloud: auf main aufsetzen
    git pull --rebase --autostash -q origin main >/dev/null 2>&1
  fi
  rc=$?
  if [ $rc -ne 0 ]; then
    if in_rebase; then
      git rebase --abort >/dev/null 2>&1
      say "Konflikt beim Abgleich mit GitHub - abgebrochen, nichts ueberschrieben. Bitte manuell klaeren."
    else
      say "Abgleich mit GitHub nicht moeglich (offline?) - arbeite mit lokalem Stand weiter."
    fi
    return 1
  fi
  return 0
}

if in_rebase; then
  say "Ein Git-Rebase ist noch offen - Sync uebersprungen."
  exit 0
fi

case "$mode" in
  pull)
    pull
    ;;
  push)
    git add -A >/dev/null 2>&1
    # Schutz: Secrets und Riesendateien (>50 MB) nie committen
    git diff --cached --name-only --diff-filter=AM -z 2>/dev/null | while IFS= read -r -d '' f; do
      case "$(basename "$f")" in .env|.env.*) git reset -q -- "$f"; continue ;; esac
      if [ -f "$f" ] && [ "$(wc -c < "$f")" -gt 52428800 ]; then git reset -q -- "$f"; fi
    done
    if ! git diff --cached --quiet 2>/dev/null; then
      host="${COMPUTERNAME:-${HOSTNAME:-$(hostname 2>/dev/null || echo cloud)}}"
      git commit -q -m "auto-sync $host $(date '+%Y-%m-%d %H:%M')" >/dev/null 2>&1
    fi
    # Nur pushen, wenn es etwas zu pushen gibt
    if has_upstream && [ "$(git rev-list --count '@{u}..HEAD' 2>/dev/null)" = "0" ]; then exit 0; fi
    if ! git push -q -u origin HEAD >/dev/null 2>&1; then
      # Remote ist weiter: erst abgleichen, dann nochmal pushen
      pull && { git push -q -u origin HEAD >/dev/null 2>&1 || say "Push fehlgeschlagen (offline?) - wird beim naechsten Mal nachgeholt."; }
    fi
    ;;
esac
exit 0
