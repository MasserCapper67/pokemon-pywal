#!/bin/sh
# Installs pokemon-pywal for the current user. Run it from a clone of the repository: ./install.sh
set -eu

REPO_DIR=$(cd "$(dirname "$0")" && pwd)
DATA_DIR=${XDG_DATA_HOME:-$HOME/.local/share}/pokemon-pywal
CACHE_DIR=${XDG_CACHE_HOME:-$HOME/.cache}/pokemon-pywal
NOCTALIA_CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}/noctalia/config.toml
BIN_DIR=$HOME/.local/bin

info() { printf '\033[1;34m::\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m::\033[0m %s\n' "$*" >&2; }

# Reads an answer from the terminal, even when stdin is not interactive. Fails without a terminal.
ask() {
    REPLY=""
    { printf '%s' "$1" >/dev/tty && read -r REPLY </dev/tty; } 2>/dev/null
}

if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is required. Install it and run this script again."
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))'; then
    warn "Python 3.8 or newer is required."
    exit 1
fi

# 1. Command
if command -v pipx >/dev/null 2>&1; then
    info "Installing with pipx..."
    pipx install --force "$REPO_DIR" >/dev/null
    PROGRAM=$(command -v pokemon-pywal || echo "$BIN_DIR/pokemon-pywal")
else
    info "Installing to $DATA_DIR..."
    mkdir -p "$DATA_DIR" "$BIN_DIR"
    rm -rf "$DATA_DIR/pokemon_pywal"
    cp -r "$REPO_DIR/pokemon_pywal" "$DATA_DIR/"
    PROGRAM=$BIN_DIR/pokemon-pywal
    # -S skips loading site-packages, which only stdlib-based code like this can do, to start faster
    cat >"$PROGRAM" <<EOF
#!/bin/sh
PYTHONPATH="$DATA_DIR" exec python3 -S -c 'from pokemon_pywal import main; main()' "\$@"
EOF
    chmod +x "$PROGRAM"
fi
info "Installed $PROGRAM"

# 2. Sprites
if [ -d /usr/local/opt/pokemon-colorscripts-fork ] || [ -d /opt/pokemon-colorscripts ] \
    || [ -d /usr/local/opt/pokemon-colorscripts ]; then
    info "Using the installed pokemon-colorscripts sprites"
else
    "$PROGRAM" --download-sprites
fi

# 3. Fastfetch
if command -v fastfetch >/dev/null 2>&1; then
    while :; do
        ask "Fastfetch preset to use (a number like 13, a name like neofetch, or Enter to skip): " || break
        [ -z "$REPLY" ] && break
        "$PROGRAM" --fastfetch "$REPLY" && break
    done
fi

# 4. Noctalia hook
if command -v noctalia >/dev/null 2>&1; then
    mkdir -p "$DATA_DIR"
    cp "$REPO_DIR/noctalia/pokemon-pywal.json" "$DATA_DIR/noctalia-template.json"

    # Earlier versions of this script wrote the hook under a section Noctalia ignores
    if [ -f "$NOCTALIA_CONFIG" ] && grep -q '^\[templates\.pokemon-pywal\]$' "$NOCTALIA_CONFIG"; then
        sed -i.bak '/^\[templates\.pokemon-pywal\]$/,/^post_hook = /d' "$NOCTALIA_CONFIG"
        info "Removed an invalid hook from $NOCTALIA_CONFIG (backup: $NOCTALIA_CONFIG.bak)"
    fi

    # Number of Pokémon saved per palette; one of them is shown at random
    COUNT=
    while :; do
        ask "How many Pokémon to save for each wallpaper, 1-5 (Enter keeps the current number, 4 by default)? " || break
        case $REPLY in
            '') break ;;
            [1-5]) COUNT=$REPLY; break ;;
            *) warn "Enter a number from 1 to 5." ;;
        esac
    done
    HOOK_COMMAND="\"$PROGRAM\" --save-sprite${COUNT:+ --count $COUNT}"

    if [ -f "$NOCTALIA_CONFIG" ] && grep -q '^\[theme\.templates\.user\.pokemon-pywal\]$' "$NOCTALIA_CONFIG"; then
        if [ -n "$COUNT" ]; then
            sed -i "/^\[theme\.templates\.user\.pokemon-pywal\]$/,/^post_hook = /s|^post_hook = .*|post_hook = '$HOOK_COMMAND'|" \
                "$NOCTALIA_CONFIG"
            info "Noctalia hook already set up in $NOCTALIA_CONFIG, now saving $COUNT Pokémon"
        else
            info "Noctalia hook already set up in $NOCTALIA_CONFIG"
        fi
        HOOK=yes
    else
        ask "Add the Noctalia hook to $NOCTALIA_CONFIG so the Pokémon follows your palette? [Y/n] " || REPLY=n
        case $REPLY in
            [nN]*)
                info "Skipped the Noctalia hook. See the README to add it by hand."
                HOOK=no
                ;;
            *)
                mkdir -p "$(dirname "$NOCTALIA_CONFIG")"
                cat >>"$NOCTALIA_CONFIG" <<EOF

[theme.templates.user.pokemon-pywal]
input_path = "$DATA_DIR/noctalia-template.json"
output_path = "$CACHE_DIR/colors.json"
post_hook = '$HOOK_COMMAND'
EOF
                info "Added the hook to $NOCTALIA_CONFIG"
                HOOK=yes
                ;;
        esac
    fi

    if [ "$HOOK" = yes ]; then
        if noctalia config validate "$NOCTALIA_CONFIG" 2>&1 | grep -q 'pokemon-pywal'; then
            warn "Noctalia reports a problem with the hook:"
            noctalia config validate "$NOCTALIA_CONFIG" 2>&1 | grep 'pokemon-pywal' >&2
        elif noctalia msg config-reload >/dev/null 2>&1 && noctalia msg templates-apply >/dev/null 2>&1; then
            # The hook runs in the background, so wait for the sprite to appear
            i=0
            while [ ! -e "$CACHE_DIR/pokemon_sprite" ] && [ $i -lt 20 ]; do
                sleep 0.5
                i=$((i + 1))
            done
            if [ -e "$CACHE_DIR/pokemon_sprite" ]; then
                info "Applied the current palette"
            else
                warn "Noctalia applied the palette but no Pokémon was saved. Check ~/.cache/noctalia/noctalia.log"
            fi
        else
            warn "Noctalia is not running; the Pokémon will be picked on the next palette change."
        fi
    fi
else
    info "Noctalia not found. Run '$PROGRAM --save-sprite' after changing your pywal colors."
fi

case ":$PATH:" in
    *":$(dirname "$PROGRAM"):"*) ;;
    *) warn "$(dirname "$PROGRAM") is not in your PATH. Add it to use 'pokemon-pywal' directly." ;;
esac

info "Done!"
