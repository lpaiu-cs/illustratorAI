from __future__ import annotations

import argparse
from pathlib import Path

CATEGORY_BUILDERS = {}


def category(name, count):
    def register(fn):
        CATEGORY_BUILDERS[name] = (count, fn)
        return fn
    return register


@category("smiley", 10)
def smiley():
    colors = ["yellow", "orange", "pink", "lime green", "cyan", "red", "purple", "gold", "light blue", "magenta"]
    mouths = ["smiling mouth", "wide open laughing mouth", "gentle smile"]
    for index in range(10):
        color = colors[index]
        mouth = mouths[index % len(mouths)]
        yield (
            f"Draw a 64x64 {color} smiley face: a {color} circle outline for the head, "
            f"two small black dot eyes, and a {mouth}."
        )


@category("house", 10)
def house():
    bodies = ["red", "blue", "brown", "green", "gray", "orange", "purple", "teal", "pink", "dark yellow"]
    extras = ["a square window", "two square windows", "a door and one window", "a chimney"]
    for index in range(10):
        body = bodies[index]
        extra = extras[index % len(extras)]
        yield (
            f"Draw a 64x64 house: a {body} square body, a dark gray triangle roof, "
            f"a small brown rectangle door, and {extra}."
        )


@category("tree", 8)
def tree():
    foliage = [
        ("green circle", "round"), ("dark green circle", "tall"),
        ("light green triangle", "pine-like"), ("olive green circle", "wide"),
        ("teal triangle", "pointy"), ("green semicircle", "bushy"),
        ("dark teal circle", "round"), ("yellow-green circle", "small round"),
    ]
    for index, (shape, _label) in enumerate(foliage):
        trunk = ["brown", "dark brown", "tan", "brown", "dark brown", "brown", "gray brown", "tan"][index]
        yield (
            f"Draw a 64x64 tree: a thin {trunk} rectangle trunk at the bottom center and a "
            f"{shape} foliage on top of it."
        )


@category("car", 9)
def car():
    colors = ["red", "blue", "green", "yellow", "black", "white with black outline", "orange", "purple", "silver gray"]
    for index in range(9):
        color = colors[index]
        yield (
            f"Draw a 64x64 car seen from the side: a long {color} rounded rectangle body, "
            f"a smaller rectangle cabin on top, and two black circle wheels."
        )


@category("flower", 8)
def flower():
    petals = ["red", "pink", "purple", "orange", "magenta", "coral", "violet", "crimson"]
    centers = ["yellow", "orange", "golden", "light yellow", "yellow", "amber", "yellow", "gold"]
    for index in range(8):
        yield (
            f"Draw a 64x64 flower: four {petals[index]} circles as petals around a "
            f"{centers[index]} circle center, with a green line stem and a small green leaf."
        )


@category("fish", 8)
def fish():
    colors = ["orange goldfish", "blue tang", "green fish", "purple fish", "red fish", "teal fish", "yellow fish", "pink fish"]
    for index in range(8):
        color = colors[index]
        yield (
            f"Draw a 64x64 {color}: an ellipse body facing left, a triangle tail on the right, "
            "a small black dot eye, and a tiny triangle fin on top."
        )


@category("boat", 8)
def boat():
    hulls = ["brown", "dark red", "navy blue", "dark green", "black", "walnut brown", "slate gray", "maroon"]
    sails = ["white triangle sail", "striped red and white triangle sail", "cream triangle sail"]
    for index in range(8):
        yield (
            f"Draw a 64x64 sailboat: a {hulls[index]} trapezoid hull at the bottom, a vertical mast line, "
            f"and a {sails[index % len(sails)]} attached to the mast."
        )


@category("robot", 9)
def robot():
    bodies = ["gray", "silver", "light blue", "green", "orange", "purple", "steel blue", "beige", "charcoal"]
    eyes = ["two round blue eyes", "two square green eyes", "one big round cyan eye"]
    for index in range(9):
        body = bodies[index]
        eye = eyes[index % len(eyes)]
        yield (
            f"Draw a 64x64 robot: a square head with {eye} and an antenna line on top, "
            f"a larger {body} rectangle body, and simple rectangle arms."
        )


@category("snowman", 6)
def snowman():
    accessories = ["a carrot nose", "a black top hat", "a red scarf", "stick arms", "three buttons", "a carrot nose and stick arms"]
    for index in range(6):
        extra = accessories[index]
        yield (
            f"Draw a 64x64 snowman: three stacked white circles with black outlines getting bigger toward the bottom, "
            f"two black dot eyes, and {extra}."
        )


@category("space", 8)
def space():
    bgs = ["very dark blue", "black", "deep purple", "midnight navy", "dark indigo", "charcoal", "dark violet", "near-black blue"]
    moons = ["a pale yellow full moon", "a gray cratered moon", "an orange planet", "a blue planet", "a ringed tan planet", "a green planet", "a red planet", "a silver crescent moon"]
    for index in range(8):
        yield (
            f"Draw a 64x64 night sky scene: fill the background with {bgs[index]}, draw {moons[index]} "
            "in the upper area, and five tiny white dots as stars."
        )


@category("kite", 8)
def kite():
    colors = ["red diamond kite", "blue diamond kite", "yellow diamond kite", "purple diamond kite",
              "green diamond kite", "orange diamond kite", "pink diamond kite", "cyan diamond kite"]
    tails = ["a wavy tail line with three small bow triangles", "a straight tail line with two bows", "a long curvy tail"]
    for index in range(8):
        yield (
            f"Draw a 64x64 flying {colors[index]} in the sky with cross lines inside it, "
            f"and {tails[index % len(tails)]} hanging below."
        )


@category("cup", 8)
def cup():
    cups = ["red mug", "blue mug", "green teacup", "purple mug", "orange mug", "pink mug", "brown coffee mug", "black mug"]
    steam = ["two wavy steam lines above it", "one wavy steam line above it", "no steam", "three short steam lines above it"]
    for index in range(8):
        yield (
            f"Draw a 64x64 {cups[index]}: a rounded rectangle cup body with a half-circle handle on the right side, "
            f"a flat saucer line under it, and {steam[index % len(steam)]}."
        )


def build_goals(total: int) -> list[str]:
    goals: list[str] = []
    for _count, builder in CATEGORY_BUILDERS.values():
        goals.extend(builder())
    unique: list[str] = []
    seen: set[str] = set()
    for goal in goals:
        if goal not in seen:
            seen.add(goal)
            unique.append(goal)
    return unique[:total]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Stage 0 goals file")
    parser.add_argument("--total", type=int, default=100, help="Take the first N unique goals")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    goals = build_goals(args.total)
    header = "# Generated Stage 0 goals (deterministic template combinations)"
    lines = [header] + goals
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(goals)} goals to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
