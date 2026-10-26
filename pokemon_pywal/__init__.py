import os
import sys
import math
import marshal

# Only stdlib modules that load in well under a millisecond are imported here; the rest
# (json, re, subprocess) are imported where they are needed, so a run stays fast.


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
DEFAULT_COUNT = 4
MAX_COUNT = 5
# Sprites taller or wider than this (in terminal cells) are skipped. ~90% of them fit.
DEFAULT_MAX_HEIGHT = 20
DEFAULT_MAX_WIDTH = 40
# Colors darker and grayer than this (CIELAB lightness and chroma) count as outline
OUTLINE_MAX_LIGHTNESS = 35
OUTLINE_MAX_CHROMA = 8
CACHE_DIR = xdg_dir("XDG_CACHE_HOME", "~/.cache")
POKEMON_SPRITE_FILE = os.path.join(CACHE_DIR, "pokemon_sprite")
POKEMON_COLORS_CACHE = os.path.join(CACHE_DIR, "pokemon_cache.marshal")
OLD_POKEMON_COLORS_CACHE = os.path.join(CACHE_DIR, "pokemon_colors_cache.json")
CACHE_VERSION = 2
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
    import subprocess
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

    # Updated sprites may have changed colors, so analyze them again on the next run
    if os.path.exists(POKEMON_COLORS_CACHE):
        os.remove(POKEMON_COLORS_CACHE)

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


def parse_flat_json(text):
    # The Noctalia template is a flat object of plain strings, so splitting on quotes is enough
    # and avoids importing json (and re). Anything else falls back to json.
    parts = text.split('"')
    if len(parts) % 2 == 0 or '\\' in text:
        return None
    strings = parts[1::2]
    return dict(zip(strings[::2], strings[1::2]))


def load_palette_colors():
    if os.path.exists(NOCTALIA_COLORS_FILE):
        with open(NOCTALIA_COLORS_FILE, 'r') as f:
            text = f.read()
        colors_data = parse_flat_json(text)
        if not colors_data or 'primary' not in colors_data or 'tertiary' not in colors_data:
            import json
            colors_data = json.loads(text)
        return [colors_data['primary'], colors_data['tertiary']]

    if os.path.exists(PYWAL_COLORS_FILE):
        import json
        with open(PYWAL_COLORS_FILE, 'r') as f:
            colors_data = json.load(f)
        return [colors_data['colors']['color3'], colors_data['colors']['color5']]

    raise SystemExit(
        f"No palette found. Expected {NOCTALIA_COLORS_FILE} (Noctalia template) "
        f"or {PYWAL_COLORS_FILE} (pywal)."
    )


def is_outline(color):
    # Black outlines and the dark gray shading next to them are in almost every sprite, so they
    # would be the most common color of most Pokémon. Dark colors with some hue are kept.
    L, a, b = hex_to_lab(color)
    return L < OUTLINE_MAX_LIGHTNESS and math.hypot(a, b) < OUTLINE_MAX_CHROMA


def xterm_color(n):
    # RGB of a 256-color palette index (the first 16 use the usual xterm values)
    if n < 16:
        base = [(0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0), (0, 0, 238), (205, 0, 205),
                (0, 205, 205), (229, 229, 229), (127, 127, 127), (255, 0, 0), (0, 255, 0),
                (255, 255, 0), (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]
        return base[n]
    if n < 232:
        n -= 16
        return tuple(0 if v == 0 else 55 + 40 * v for v in (n // 36, n // 6 % 6, n % 6))
    gray = 8 + 10 * (n - 232)
    return gray, gray, gray


def sgr_color(params, i):
    # Reads the color after a 38 or 48 code: "2;r;g;b" or "5;n". Returns it and the next index.
    if i < len(params) and params[i] == 2:
        return tuple(params[i + 1:i + 4]), i + 4
    if i < len(params) and params[i] == 5:
        return xterm_color(params[i + 1]), i + 2
    return None, i


def analyze_sprite(sprite_path):
    # Returns the most common color (ignoring outlines) and the size (height, width) of the sprite
    import re
    from collections import Counter

    with open(sprite_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Each "▀" or "▄" cell holds two pixels: the half block is the foreground color and the
    # other half is the background color, if any.
    pixels = Counter()
    fg = bg = None
    for codes, text in re.findall(r'\x1b\[([0-9;]*)m([^\x1b]*)', '\x1b[m' + content):
        params = [int(c) if c else 0 for c in codes.split(';')]
        i = 0
        while i < len(params):
            code = params[i]
            if code in (38, 48):
                color, i = sgr_color(params, i + 1)
                if code == 38:
                    fg = color
                else:
                    bg = color
                continue
            if code == 0:
                fg = bg = None
            elif code == 39:
                fg = None
            elif code == 49:
                bg = None
            i += 1
        for char in text:
            if char in '▀▄':
                pixels[fg] += 1
                pixels[bg] += 1
            elif char == ' ':
                pixels[bg] += 2
    pixels.pop(None, None)
    if not pixels:
        return None

    colors = {f"#{r:02x}{g:02x}{b:02x}": n for (r, g, b), n in pixels.items()}
    body = {color: n for color, n in colors.items() if not is_outline(color)}
    color = max(body or colors, key=(body or colors).get)

    lines = re.sub(r'\x1b\[[0-9;]*m', '', content).rstrip('\n').split('\n')
    return color, len(lines), max(len(line.rstrip()) for line in lines)


def hex_to_lab(color):
    try:
        if len(color) != 7 or color[0] != '#':
            raise ValueError
        rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    except ValueError:
        raise ValueError(f"Invalid color format: {color}") from None

    def linearize(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(c / 255) for c in rgb)

    # sRGB -> XYZ, normalized to the D65 white point
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


POW25_7 = 25 ** 7
TAU = 2 * math.pi


def delta_e_cie2000_from(lab1):
    # Returns a function giving the CIEDE2000 distance from lab1 to (L2, a2, b2). Works in radians
    # and computes the lab1 terms once, since it runs for every sprite.
    L1, a1, b1 = lab1
    c1 = math.hypot(a1, b1)
    sqrt, sin, cos, atan2, hypot = math.sqrt, math.sin, math.cos, math.atan2, math.hypot

    def delta_e(L2, a2, b2):
        c_bar_7 = ((c1 + hypot(a2, b2)) / 2) ** 7
        g = 1.5 - 0.5 * sqrt(c_bar_7 / (c_bar_7 + POW25_7))
        a1p, a2p = g * a1, g * a2
        c1p, c2p = hypot(a1p, b1), hypot(a2p, b2)
        h1p = atan2(b1, a1p) % TAU
        h2p = atan2(b2, a2p) % TAU

        if c1p * c2p == 0:
            delta_hp = 0
            h_bar_p = h1p + h2p
        else:
            delta_hp = h2p - h1p
            if delta_hp > math.pi:
                delta_hp -= TAU
            elif delta_hp < -math.pi:
                delta_hp += TAU
            if abs(h1p - h2p) <= math.pi:
                h_bar_p = (h1p + h2p) / 2
            elif h1p + h2p < TAU:
                h_bar_p = (h1p + h2p + TAU) / 2
            else:
                h_bar_p = (h1p + h2p - TAU) / 2
        delta_big_hp = 2 * sqrt(c1p * c2p) * sin(delta_hp / 2)

        l_bar_p_50 = ((L1 + L2) / 2 - 50) ** 2
        c_bar_p = (c1p + c2p) / 2
        t = (1
             - 0.17 * cos(h_bar_p - 0.5235987755982988)   # 30°
             + 0.24 * cos(2 * h_bar_p)
             + 0.32 * cos(3 * h_bar_p + 0.10471975511965977)  # 6°
             - 0.20 * cos(4 * h_bar_p - 1.0995574287564276))  # 63°
        delta_theta = 0.5235987755982988 * math.exp(-((math.degrees(h_bar_p) - 275) / 25) ** 2)
        c_bar_p_7 = c_bar_p ** 7
        r_t = -sin(2 * delta_theta) * 2 * sqrt(c_bar_p_7 / (c_bar_p_7 + POW25_7))

        dl = (L2 - L1) / (1 + 0.015 * l_bar_p_50 / sqrt(20 + l_bar_p_50))
        dc = (c2p - c1p) / (1 + 0.045 * c_bar_p)
        dh = delta_big_hp / (1 + 0.015 * c_bar_p * t)
        return sqrt(dl * dl + dc * dc + dh * dh + r_t * dc * dh)

    return delta_e


def delta_e_cie2000(lab1, lab2):
    return delta_e_cie2000_from(lab1)(*lab2)


# Largest S_L of CIEDE2000 (reached at L = 0 or 100). Since the R_T term can never make the
# distance smaller than the lightness term, CIEDE2000 >= |L1 - L2| / MAX_S_L.
MAX_S_L = 1 + 0.015 * 50 ** 2 / math.sqrt(20 + 50 ** 2)


def compare_colors(color1, color2):
    return delta_e_cie2000(hex_to_lab(color1), hex_to_lab(color2))

# The sprites are analyzed once and cached as (name, L, a, b, height, width) rows sorted by L.
# marshal is used instead of json because it loads several times faster and needs no import.
def preprocess_pokemon_colors(sprites_dir):
    pokemons = []
    for pokemon_file in sorted(os.listdir(sprites_dir)):
        info = analyze_sprite(os.path.join(sprites_dir, pokemon_file))
        if info:
            color, height, width = info
            pokemons.append((pokemon_file, *hex_to_lab(color), height, width))
    pokemons.sort(key=lambda p: p[1])

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(POKEMON_COLORS_CACHE, 'wb') as f:
        marshal.dump((CACHE_VERSION, sprites_dir, os.stat(sprites_dir).st_mtime_ns, pokemons), f)
    if os.path.exists(OLD_POKEMON_COLORS_CACHE):
        os.remove(OLD_POKEMON_COLORS_CACHE)

    return pokemons


def load_pokemon_colors(sprites_dir):
    try:
        # marshal.loads on the whole file is much faster than marshal.load on the file object
        with open(POKEMON_COLORS_CACHE, 'rb') as f:
            version, cached_dir, mtime, pokemons = marshal.loads(f.read())
        if (version, cached_dir, mtime) == (CACHE_VERSION, sprites_dir, os.stat(sprites_dir).st_mtime_ns):
            return pokemons
    except (OSError, EOFError, ValueError, TypeError):
        pass

    return preprocess_pokemon_colors(sprites_dir)


def filter_by_size(pokemons, max_height, max_width):
    return [p for p in pokemons if p[4] <= max_height and p[5] <= max_width]


def find_best_pokemons(palette_color, pokemons, count):
    # pokemons is sorted by L, so walk outwards from the palette lightness and stop as soon as
    # the lightness difference alone rules out the rest. The result is exactly the CIEDE2000
    # top `count`, but usually only a few dozen distances are computed instead of ~1500.
    import heapq
    from bisect import bisect_left

    palette_lab = hex_to_lab(palette_color)
    delta_e = delta_e_cie2000_from(palette_lab)
    L = palette_lab[0]
    lightness = [p[1] for p in pokemons]
    above = bisect_left(lightness, L)
    below = above - 1
    best = []  # max-heap of (-distance, name) with the `count` closest so far

    while below >= 0 or above < len(pokemons):
        if above == len(pokemons) or (below >= 0 and L - lightness[below] <= lightness[above] - L):
            pokemon = pokemons[below]
            below -= 1
        else:
            pokemon = pokemons[above]
            above += 1

        if len(best) == count and abs(pokemon[1] - L) / MAX_S_L > -best[0][0]:
            break
        distance = delta_e(pokemon[1], pokemon[2], pokemon[3])
        if len(best) < count:
            heapq.heappush(best, (-distance, pokemon[0]))
        elif distance < -best[0][0]:
            heapq.heapreplace(best, (-distance, pokemon[0]))

    return [name for _, name in sorted(best, key=lambda item: (-item[0], item[1]))]


def select_pokemons(colors, pokemons, count):
    # Alternates between the best matches of each palette color, skipping repeats
    rankings = [find_best_pokemons(color, pokemons, count) for color in colors]
    selected = []
    for i in range(count):
        for ranking in rankings:
            if i < len(ranking) and ranking[i] not in selected:
                selected.append(ranking[i])
    return selected[:count]

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
    # Points pokemon_sprite to a random saved sprite, other than the current one when there are
    # several, and returns its path (None if there are no saved sprites)
    try:
        pokemon_sprites = [f for f in os.listdir(CACHE_DIR) if f.startswith("pokemon_sprite_")]
    except FileNotFoundError:
        pokemon_sprites = []
    if not pokemon_sprites:
        print("No Pokemon sprites found in cache.", file=sys.stderr)
        return None

    try:
        current = os.path.basename(os.readlink(POKEMON_SPRITE_FILE))
    except OSError:
        current = None
    if len(pokemon_sprites) > 1 and current in pokemon_sprites:
        pokemon_sprites.remove(current)

    # os.urandom instead of the random module, which takes longer to import
    selected_pokemon = pokemon_sprites[int.from_bytes(os.urandom(4), 'little') % len(pokemon_sprites)]
    selected_path = os.path.join(CACHE_DIR, selected_pokemon)

    # Replaced atomically, so terminals opened at the same time never see it missing
    temp_link = f"{POKEMON_SPRITE_FILE}.{os.getpid()}"
    try:
        os.symlink(selected_path, temp_link)
        os.replace(temp_link, POKEMON_SPRITE_FILE)
    except OSError as e:
        print(f"Error creating symlink: {e}", file=sys.stderr)
    return selected_path

def print_random_sprite():
    selected_path = change_symlink()
    if selected_path:
        with open(selected_path, 'r', encoding='utf-8') as f:
            sys.stdout.write(f.read())

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
    import json
    preset_path = find_fastfetch_preset(preset)
    with open(preset_path, 'r', encoding='utf-8') as f:
        config = json.loads(strip_jsonc(f.read()))

    # The logo is the sprite chosen in advance, shown with a plain cat so no Python runs before it
    # appears. Then the sprite for the next terminal is chosen in the background.
    import shlex
    import shutil
    program = shutil.which("pokemon-pywal") or "pokemon-pywal"
    logo = {
        "type": "command-raw",
        "source": f"cat {shlex.quote(POKEMON_SPRITE_FILE)} 2>/dev/null; "
                  f"{shlex.quote(program)} --change-symlink >/dev/null 2>&1 &",
    }
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

# argparse is not used because on recent Python versions it alone takes longer to load than
# everything else this program does.
OPTIONS = [
    # (flag, value name or None for switches, help)
    ('--save-sprite', None, 'Save the selected Pokémon sprites to files.'),
    ('--count', 'N', f'Number of Pokémon to save, from 1 to {MAX_COUNT} (default {DEFAULT_COUNT}). '
                     'One of them is shown at random.'),
    ('--max-height', 'LINES', f'Skip sprites taller than LINES (default {DEFAULT_MAX_HEIGHT}).'),
    ('--max-width', 'COLUMNS', f'Skip sprites wider than COLUMNS (default {DEFAULT_MAX_WIDTH}).'),
    ('--change-symlink', None, 'Changes symlink to a random saved sprite.'),
    ('--random-sprite', None, 'Change the symlink to a random saved sprite and print it (used by fastfetch).'),
    ('--sprites-dir', 'PATH', 'pokemon-colorscripts sprites directory (also POKEMON_SPRITES_DIR).'),
    ('--download-sprites', None, 'Download or update the Pokémon sprites.'),
    ('--fastfetch', 'PRESET', 'Create a fastfetch config from PRESET (e.g. 13, neofetch or a path) '
                              'with the Pokémon as logo.'),
]


def print_help():
    print("usage: pokemon-pywal [options]\n")
    print("Select a Pokémon sprite based on your Noctalia (or pywal) palette.\n\noptions:")
    print(f"  {'-h, --help':<26}Show this help message and exit.")
    for flag, metavar, help_text in OPTIONS:
        print(f"  {flag + (' ' + metavar if metavar else ''):<26}{help_text}")


def parse_args(argv):
    takes_value = {flag: metavar is not None for flag, metavar, _ in OPTIONS}
    args = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('-h', '--help'):
            print_help()
            raise SystemExit(0)
        flag, has_value, value = arg.partition('=')
        if flag not in takes_value:
            raise SystemExit(f"pokemon-pywal: unknown option {arg}. See pokemon-pywal --help")
        if takes_value[flag] and not has_value:
            i += 1
            if i == len(argv):
                raise SystemExit(f"pokemon-pywal: {flag} needs a value")
            value = argv[i]
        elif not takes_value[flag] and has_value:
            raise SystemExit(f"pokemon-pywal: {flag} does not take a value")
        args[flag] = value if takes_value[flag] else True
        i += 1
    return args


def int_option(args, flag, default, minimum, maximum=None):
    value = args.get(flag, default)
    try:
        value = int(value)
    except ValueError:
        value = None
    if value is None or value < minimum or (maximum is not None and value > maximum):
        limits = f"from {minimum} to {maximum}" if maximum is not None else f"at least {minimum}"
        raise SystemExit(f"pokemon-pywal: {flag} must be a number {limits}")
    return value


def main():
    args = parse_args(sys.argv[1:])
    count = int_option(args, '--count', DEFAULT_COUNT, 1, MAX_COUNT)
    max_height = int_option(args, '--max-height', DEFAULT_MAX_HEIGHT, 1)
    max_width = int_option(args, '--max-width', DEFAULT_MAX_WIDTH, 1)

    if args.get('--download-sprites'):
        download_sprites()
        return

    if '--fastfetch' in args:
        write_fastfetch_config(args['--fastfetch'])
        return

    if args.get('--change-symlink'):
        change_symlink()
        return

    if args.get('--random-sprite'):
        print_random_sprite()
        return

    colors = load_palette_colors()
    sprites_dir = find_sprites_dir(args.get('--sprites-dir'))
    pokemons = filter_by_size(load_pokemon_colors(sprites_dir), max_height, max_width)
    best_pokemons = select_pokemons(colors, pokemons, count)

    if best_pokemons:
        if args.get('--save-sprite'):
            remove_saved_sprites()
        for i, pokemon_file in enumerate(best_pokemons):
            print(f"Selected Pokemon {i+1}: {pokemon_file}")
            if args.get('--save-sprite'):
                target_path = os.path.join(CACHE_DIR, f"pokemon_sprite_{i+1}")
                save_pokemon_sprite(os.path.join(sprites_dir, pokemon_file), target_path)
        change_symlink()

    else:
        print("No Pokémon found. Try a larger --max-height or --max-width.")

if __name__ == "__main__":
    main()
