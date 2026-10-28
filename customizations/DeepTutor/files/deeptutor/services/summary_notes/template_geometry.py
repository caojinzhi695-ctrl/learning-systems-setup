"""Safe text widths in Manim frame units, derived from the reference geometry.

Character counts are only a cheap precheck. Pango measures the actual glyphs
in manim_exact_scene.py before drawing; a five-character label is not rejected
just because the original numeric example had four characters.
"""


def slot_width(layout, key, declared=None):
    if declared is not None:
        return declared
    if not key.startswith('body_'):
        return {'title':14.2, 'subtitle':14.4, 'caption':13.9, 'note':14.2}[key]
    index = int(key[5:])
    if layout == 'principles':
        return 2.8
    if layout == 'demand':
        return 1.8 if index >= 10 else 4.05
    if layout == 'competition':
        return 12.9 if index == 7 else 4.1
    if layout == 'profit':
        return 14 if index == 10 else 3.9
    if layout == 'reputation':
        return 14 if index == 10 else 4.0
    if layout == 'logistics':
        return 4.3 if index == 1 else 1.0 if index <= 4 else 6.0
    if layout == 'compliance':
        return 6.4
    if layout == 'overview':
        return 14 if index == 1 else 2.8
    raise ValueError(f'Unknown template layout: {layout}')


def text_capacity(layout, key, slot):
    # Chinese glyph advance is about font_size/72 frame units in Manim.
    # Actual glyph width is authoritative; this estimate leaves 10% tolerance.
    width = slot_width(layout, key, slot.get('width'))
    return round(max(slot['max_units'], width * 72 / slot['font_size']) * 1.1, 2)
