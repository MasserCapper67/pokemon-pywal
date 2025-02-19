import numpy as np
import os
import re
import json
import random
import argparse
from collections import Counter
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_diff import delta_e_cie2000
from colormath.color_conversions import convert_color

POKEMON_SPRITES_DIR = "/opt/pokemon-colorscripts/colorscripts/small/regular"
TOP_N_POKEMONS = 2
POKEMON_SPRITE_FILE = os.path.expanduser("~/.cache/wal/pokemon_sprite")
POKEMON_COLORS_CACHE = os.path.expanduser("~/.cache/wal/pokemon_colors_cache.json")

def load_pywal_color_5():
    with open(f"{os.getenv('HOME')}/.cache/wal/colors.json", 'r') as f:
        colors_data = json.load(f)
        return colors_data['colors'].get('color5')


def load_pywal_colors():

    colors = []

    with open(f"{os.getenv('HOME')}/.cache/wal/colors.json", 'r') as f:
        colors_data = json.load(f)

        colors.append(colors_data['colors'].get('color3'))
        colors.append(colors_data['colors'].get('color5'))

    return colors


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


def compare_colors(color1, color2):
    if not (color1.startswith('#') and color2.startswith('#')):
        raise ValueError(f"Invalid color format: {color1} or {color2}")
    color1_lab = convert_color(sRGBColor.new_from_rgb_hex(color1), LabColor)
    color2_lab = convert_color(sRGBColor.new_from_rgb_hex(color2), LabColor)
    delta_e = delta_e_cie2000(color1_lab, color2_lab)

    return delta_e.item() if hasattr(delta_e, 'item') else delta_e

# Uso esta función para meter los colores en cache e intentar agilizar el proceso
def preprocess_pokemon_colors():
    pokemon_colors_cache = {}
    for pokemon_file in os.listdir(POKEMON_SPRITES_DIR):
        sprite_path = os.path.join(POKEMON_SPRITES_DIR, pokemon_file)
        most_common_color = extract_colors_from_sprite(sprite_path)
        if most_common_color:
            pokemon_colors_cache[pokemon_file] = most_common_color

    with open(POKEMON_COLORS_CACHE, 'w') as f:
        json.dump(pokemon_colors_cache, f)

def find_best_pokemons(pywal_color):
    with open(POKEMON_COLORS_CACHE, 'r') as f:
        pokemon_colors_cache = json.load(f)

    best_pokemons = sorted(
        pokemon_colors_cache.items(),
        key=lambda item: compare_colors(pywal_color, item[1])
    )[:TOP_N_POKEMONS]

    return [pokemon[0] for pokemon in best_pokemons]

def save_pokemon_sprite(pokemon_file, target_path):
    sprite_path = os.path.join(POKEMON_SPRITES_DIR, pokemon_file)
    with open(sprite_path, 'r', encoding='utf-8') as f:
        pokemon_sprite = f.read()
    with open(target_path, 'w', encoding = 'utf-8') as f:
        f.write(pokemon_sprite)
    print(f"Pokemon sprite saved to {target_path}")

def change_symlink():
    pokemon_sprites_dir = os.path.expanduser("~/.cache/wal/")

    pokemon_sprites = [
        f for f in os.listdir(pokemon_sprites_dir)
        if f.startswith("pokemon_sprite_")
    ]
    if pokemon_sprites:
        selected_pokemon = random.choice(pokemon_sprites)
        selected_path = os.path.join(pokemon_sprites_dir, selected_pokemon)

        symlink_path = os.path.expanduser("~/.cache/wal/pokemon_sprite")
        if os.path.exists(symlink_path) or os.path.islink(symlink_path):
            try:
                os.unlink(symlink_path)
            except Exception as e:
                print(f"Error removing symlink: {e}")
        try:
            os.symlink(selected_path, symlink_path)
        except Exception as e:
            print(f"Error creating symlink: {e}")

    else:
        print("No Pokemon sprites found in cache.")

def main():
    parser = argparse.ArgumentParser(description="Select a Pokémon sprite based on Pywal colors.")
    parser.add_argument('--save-sprite', action='store_true', help='Save the selected Pokémon sprite to a file.')
    parser.add_argument('--change-symlink', action='store_true', help='Changes symlink to a random saved sprite.')

    args = parser.parse_args()

    if args.change_symlink:
        change_symlink()
        return
    colors = load_pywal_colors()

    if not os.path.exists(POKEMON_COLORS_CACHE):
        preprocess_pokemon_colors()

    best_pokemons = []
    for color in colors:
        best_pokemons.append(find_best_pokemons(color))
   
    best_pokemons = sum(best_pokemons, [])

    if best_pokemons:
        for i, pokemon_file in enumerate(best_pokemons):
            print(f"Selected Pokemon {i+1}: {pokemon_file}")
            if args.save_sprite:
                target_path = os.path.expanduser(f"~/.cache/wal/pokemon_sprite_{i+1}")
                save_pokemon_sprite(pokemon_file, target_path)
                os.system(f"cat {os.path.join(POKEMON_SPRITES_DIR, pokemon_file)}")
        change_symlink()

    else:
        print("No Pokémon found.")

if __name__ == "__main__":
    main()

