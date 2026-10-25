import os
import re
import json
import math
import random
import argparse
import subprocess
from collections import Counter


def xdg_dir(env, default):
    return os.path.join(os.getenv(env) or os.path.expanduser(default), "pokemon-pywal")


SPRITES_REPO = "https://github.com/AnarchistHoneybun/pokemon-colorscripts-fork.git"
SPRITES_SUBDIR = "colorscripts/small/regular"
DATA_DIR = xdg_dir("XDG_DATA_HOME", "~/.local/share")
DOWNLOADED_SPRITES_REPO = os.path.join(DATA_DIR, "pokemon-colorscripts")
DEFAULT_SPRITES_DIRS = [
    f"/usr/local/opt/pokemon-colorscripts-fork/{SPRITES_SUBDIR}",
    f"/opt/pokemon-colorscripts/{SPRITES_SUBDIR}",
    f"/usr/local/opt/pokemon-colorscripts/{SPRITES_SUBDIR}",
    os.path.join(DOWNLOADED_SPRITES_REPO, SPRITES_SUBDIR),
]
TOP_N_POKEMONS = 2
CACHE_DIR = xdg_dir("XDG_CACHE_HOME", "~/.cache")
POKEMON_SPRITE_FILE = os.path.join(CACHE_DIR, "pokemon_sprite")
POKEMON_COLORS_CACHE = os.path.join(CACHE_DIR, "pokemon_colors_cache.json")
# Written by the Noctalia user template (noctalia/pokemon-pywal.json)
NOCTALIA_COLORS_FILE = os.path.join(CACHE_DIR, "colors.json")
PYWAL_COLORS_FILE = os.path.expanduser("~/.cache/wal/colors.json")
FASTFETCH_PRESET_DIRS = [
    os.path.join(d, "fastfetch", "presets")
    for d in [os.getenv("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")]
    + (os.getenv("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    + ["/opt/homebrew/share"]
]
FASTFETCH_CONFIG = os.path.join(
    os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "fastfetch", "pokemon.jsonc"
)


def git(*args):
    try:
        subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("git is needed to download the Pokémon sprites. Install git and try again.")
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"Failed to download the Pokémon sprites:\n{e.stderr.strip()}")


def download_sprites():
    if os.path.isdir(os.path.join(DOWNLOADED_SPRITES_REPO, ".git")):
        print("Updating Pokémon sprites...")
        git("-C", DOWNLOADED_SPRITES_REPO, "pull", "--ff-only")
    else:
        print(f"Downloading Pokémon sprites to {DOWNLOADED_SPRITES_REPO}...")
        git("clone", "--depth", "1", "--filter=blob:none", "--sparse", SPRITES_REPO, DOWNLOADED_SPRITES_REPO)
        git("-C", DOWNLOADED_SPRITES_REPO, "sparse-checkout", "set", SPRITES_SUBDIR)

    return os.path.join(DOWNLOADED_SPRITES_REPO, SPRITES_SUBDIR)


def find_sprites_dir(override=None):
    override = override or os.getenv("POKEMON_SPRITES_DIR")
    if override:
        path = os.path.expanduser(override)
        if not os.path.isdir(path):
            raise SystemExit(f"Pokémon sprites directory not found: {path}")
        return path

    for path in DEFAULT_SPRITES_DIRS:
        if os.path.isdir(path):
            return path

    return download_sprites()


def load_palette_colors():
    if os.path.exists(NOCTALIA_COLORS_FILE):
        with open(NOCTALIA_COLORS_FILE, 'r') as f:
            colors_data = json.load(f)
        return [colors_data['primary'], colors_data['tertiary']]

    if os.path.exists(PYWAL_COLORS_FILE):
        with open(PYWAL_COLORS_FILE, 'r') as f:
            colors_data = json.load(f)
        return [colors_data['colors']['color3'], colors_data['colors']['color5']]

    raise SystemExit(
        f"No palette found. Expected {NOCTALIA_COLORS_FILE} (Noctalia template) "
        f"or {PYWAL_COLORS_FILE} (pywal)."
    )


def extract_colors_from_sprite(sprite_path):
    with open(sprite_path, 'r', encoding='utf-8') as f:
        content = f.read()

        color_pattern = re.compile(r'\x1b\[38;2;(\d+);(\d+);(\d+)m')
        matches = color_pattern.findall(content)

    color_counts = Counter(matches)
    most_common_color = color_counts.most_common(1)[0][0] if color_counts else None

    if most_common_color:
        r, g, b = most_common_color
        try:
            color = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
            return color
        except ValueError:
            return None
    return None


def hex_to_lab(color):
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError(f"Invalid color format: {color}")

    def linearize(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(int(color[i:i + 2], 16) / 255) for i in (1, 3, 5))

    # sRGB -> XYZ, normalized to the D65 white point
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e_cie2000(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar ** 7 / (c_bar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360

    delta_lp = L2 - L1
    delta_cp = c2p - c1p
    if c1p * c2p == 0:
        delta_hp = 0
    else:
        delta_hp = h2p - h1p
        if delta_hp > 180:
            delta_hp -= 360
        elif delta_hp < -180:
            delta_hp += 360
    delta_big_hp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(delta_hp / 2))

    l_bar_p = (L1 + L2) / 2
    c_bar_p = (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_bar_p = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar_p = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        h_bar_p = (h1p + h2p + 360) / 2
    else:
        h_bar_p = (h1p + h2p - 360) / 2

    t = (1
         - 0.17 * math.cos(math.radians(h_bar_p - 30))
         + 0.24 * math.cos(math.radians(2 * h_bar_p))
         + 0.32 * math.cos(math.radians(3 * h_bar_p + 6))
         - 0.20 * math.cos(math.radians(4 * h_bar_p - 63)))
    delta_theta = 30 * math.exp(-((h_bar_p - 275) / 25) ** 2)
    r_c = 2 * math.sqrt(c_bar_p ** 7 / (c_bar_p ** 7 + 25 ** 7))
    s_l = 1 + 0.015 * (l_bar_p - 50) ** 2 / math.sqrt(20 + (l_bar_p - 50) ** 2)
    s_c = 1 + 0.045 * c_bar_p
    s_h = 1 + 0.015 * c_bar_p * t
    r_t = -math.sin(math.radians(2 * delta_theta)) * r_c

    return math.sqrt(
        (delta_lp / s_l) ** 2
        + (delta_cp / s_c) ** 2
        + (delta_big_hp / s_h) ** 2
        + r_t * (delta_cp / s_c) * (delta_big_hp / s_h)
    )


def compare_colors(color1, color2):
    return delta_e_cie2000(hex_to_lab(color1), hex_to_lab(color2))

# Uso esta función para meter los colores en cache e intentar agilizar el proceso
def preprocess_pokemon_colors(sprites_dir):
    pokemon_colors = {}
    for pokemon_file in os.listdir(sprites_dir):
        sprite_path = os.path.join(sprites_dir, pokemon_file)
        most_common_color = extract_colors_from_sprite(sprite_path)
        if most_common_color:
            pokemon_colors[pokemon_file] = most_common_color

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(POKEMON_COLORS_CACHE, 'w') as f:
        json.dump({"sprites_dir": sprites_dir, "colors": pokemon_colors}, f)

    return pokemon_colors


def load_pokemon_colors(sprites_dir):
    if os.path.exists(POKEMON_COLORS_CACHE):
        with open(POKEMON_COLORS_CACHE, 'r') as f:
            cache = json.load(f)
        if cache.get("sprites_dir") == sprites_dir:
            return cache["colors"]

    return preprocess_pokemon_colors(sprites_dir)


def find_best_pokemons(palette_color, pokemon_colors):
    palette_lab = hex_to_lab(palette_color)

    best_pokemons = sorted(
        pokemon_colors.items(),
        key=lambda item: delta_e_cie2000(palette_lab, hex_to_lab(item[1]))
    )[:TOP_N_POKEMONS]

    return [pokemon[0] for pokemon in best_pokemons]

def save_pokemon_sprite(sprite_path, target_path):
    with open(sprite_path, 'r', encoding='utf-8') as f:
        pokemon_sprite = f.read()
    with open(target_path, 'w', encoding = 'utf-8') as f:
        f.write(pokemon_sprite)
    print(f"Pokemon sprite saved to {target_path}")
    print(pokemon_sprite, end="")

def remove_saved_sprites():
    for f in os.listdir(CACHE_DIR):
        if f.startswith("pokemon_sprite_"):
            os.remove(os.path.join(CACHE_DIR, f))

def change_symlink():
    if not os.path.isdir(CACHE_DIR):
        print("No Pokemon sprites found in cache.")
        return

    pokemon_sprites = [
        f for f in os.listdir(CACHE_DIR)
        if f.startswith("pokemon_sprite_")
    ]
    if pokemon_sprites:
        selected_pokemon = random.choice(pokemon_sprites)
        selected_path = os.path.join(CACHE_DIR, selected_pokemon)

        if os.path.exists(POKEMON_SPRITE_FILE) or os.path.islink(POKEMON_SPRITE_FILE):
            try:
                os.unlink(POKEMON_SPRITE_FILE)
            except Exception as e:
                print(f"Error removing symlink: {e}")
        try:
            os.symlink(selected_path, POKEMON_SPRITE_FILE)
        except Exception as e:
            print(f"Error creating symlink: {e}")

    else:
        print("No Pokemon sprites found in cache.")

def string_end(text, i):
    # Index just past the JSON string starting at text[i]
    j = i + 1
    while j < len(text) and text[j] != '"':
        j += 2 if text[j] == '\\' else 1
    return j + 1

def strip_jsonc(text):
    # Removes comments, leaving strings untouched
    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == '"':
            j = string_end(text, i)
            out.append(text[i:j])
            i = j
        elif text.startswith('//', i):
            j = text.find('\n', i)
            i = n if j == -1 else j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            i = n if j == -1 else j + 2
        else:
            out.append(text[i])
            i += 1

    return remove_trailing_commas(''.join(out))

def remove_trailing_commas(text):
    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == '"':
            j = string_end(text, i)
            out.append(text[i:j])
            i = j
            continue
        if text[i] == ',' and text[i + 1:].lstrip()[:1] in ('}', ']'):
            i += 1
            continue
        out.append(text[i])
        i += 1
    return ''.join(out)

def find_fastfetch_preset(preset):
    path = os.path.expanduser(preset)
    if os.path.isfile(path):
        return path

    if preset.isdigit():
        names = [f"examples/{preset}.jsonc"]
    else:
        names = [f"{preset}.jsonc", preset, f"examples/{preset}.jsonc"]

    for preset_dir in FASTFETCH_PRESET_DIRS:
        for name in names:
            path = os.path.join(preset_dir, name)
            if os.path.isfile(path):
                return path

    raise SystemExit(
        f"Fastfetch preset '{preset}' not found. Use a number from examples (e.g. 13), "
        "a preset name (see `fastfetch --list-presets`) or a path to a .jsonc file."
    )

def write_fastfetch_config(preset):
    preset_path = find_fastfetch_preset(preset)
    with open(preset_path, 'r', encoding='utf-8') as f:
        config = json.loads(strip_jsonc(f.read()))

    logo = {"type": "file-raw", "source": POKEMON_SPRITE_FILE}
    old_logo = config.get("logo")
    if isinstance(old_logo, dict) and "padding" in old_logo:
        logo["padding"] = old_logo["padding"]
    config["logo"] = logo

    os.makedirs(os.path.dirname(FASTFETCH_CONFIG), exist_ok=True)
    with open(FASTFETCH_CONFIG, 'w', encoding='utf-8') as f:
        f.write(f"// Generated by pokemon-pywal from {preset_path}\n")
        json.dump(config, f, indent=4, ensure_ascii=False)
        f.write("\n")

    print(f"Fastfetch config saved to {FASTFETCH_CONFIG}")
    print("Run it with: fastfetch -c pokemon")

def main():
    parser = argparse.ArgumentParser(prog='pokemon-pywal', description="Select a Pokémon sprite based on your Noctalia (or pywal) palette.")
    parser.add_argument('--save-sprite', action='store_true', help='Save the selected Pokémon sprite to a file.')
    parser.add_argument('--change-symlink', action='store_true', help='Changes symlink to a random saved sprite.')
    parser.add_argument('--sprites-dir', help='pokemon-colorscripts sprites directory (also POKEMON_SPRITES_DIR).')
    parser.add_argument('--download-sprites', action='store_true', help='Download or update the Pokémon sprites.')
    parser.add_argument('--fastfetch', metavar='PRESET', help='Create a fastfetch config from PRESET (e.g. 13, neofetch or a path) with the Pokémon as logo.')

    args = parser.parse_args()

    if args.download_sprites:
        download_sprites()
        return

    if args.fastfetch:
        write_fastfetch_config(args.fastfetch)
        return

    if args.change_symlink:
        change_symlink()
        return

    colors = load_palette_colors()
    sprites_dir = find_sprites_dir(args.sprites_dir)
    pokemon_colors = load_pokemon_colors(sprites_dir)

    best_pokemons = []
    for color in colors:
        best_pokemons.append(find_best_pokemons(color, pokemon_colors))

    best_pokemons = sum(best_pokemons, [])

    if best_pokemons:
        if args.save_sprite:
            remove_saved_sprites()
        for i, pokemon_file in enumerate(best_pokemons):
            print(f"Selected Pokemon {i+1}: {pokemon_file}")
            if args.save_sprite:
                target_path = os.path.join(CACHE_DIR, f"pokemon_sprite_{i+1}")
                save_pokemon_sprite(os.path.join(sprites_dir, pokemon_file), target_path)
        change_symlink()

    else:
        print("No Pokémon found.")

if __name__ == "__main__":
    main()
