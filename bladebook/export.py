"""
bladebook/export.py — the public projection: private core, generated public
shell. build_public() writes a static bundle: knives.json (whitelisted
fields ONLY) + re-encoded, EXIF-stripped hero images. The public tier never
touches the DB — publishing is a deliberate regeneration step.
"""

import io
import json
import os
from datetime import datetime, timezone

from PIL import Image, ImageOps, UnidentifiedImageError

from bladebook import db, photos

# Everything a fellow collector legitimately needs — and nothing else.
_PUBLIC_FIELDS = [
    'tag', 'family', 'model', 'generation', 'size', 'blade_shape',
    'knife_type', 'born_on', 'born_on_precision', 'steel', 'hardness_note',
    'damascus_smith', 'damascus_pattern', 'handle_treatment', 'graphic_name',
    'inlay_material', 'inlay_note', 'surface_finish', 'special_edition',
    'edition_number', 'hand', 'condition',
    'has_box', 'has_card', 'has_papers', 'has_pouch', 'has_lanyard',
    'notes_public',
]

DISPLAY_EDGE = 1600
THUMB_EDGE = 320


def _public_dir():
    return os.environ.get('BLADEBOOK_PUBLIC_DIR',
                          os.path.join(os.getcwd(), 'public'))


def _orig_dir(tag):
    return os.path.join(os.environ.get('BLADEBOOK_DATA_DIR', os.path.join(os.getcwd(), 'data')),
                        'originals', tag)


def _export_images(k, img_dir):
    """Re-encoded (EXIF/GPS-free) display + thumb for the hero photo.
    Returns (hero_name, thumb_name) or (None, None)."""
    names = photos.list_photos(_orig_dir(k['tag']))
    if not names:
        return None, None
    hero = k['hero_photo'] if k['hero_photo'] in names else names[-1]
    try:
        with open(os.path.join(_orig_dir(k['tag']), hero), 'rb') as f:
            img = Image.open(io.BytesIO(f.read()))
            img = ImageOps.exif_transpose(img)
            img = img.convert('RGB')          # re-encode: all metadata dropped
    except (OSError, UnidentifiedImageError):
        return None, None
    os.makedirs(img_dir, exist_ok=True)
    out, out_t = f"{k['tag']}.jpg", f"{k['tag']}_t.jpg"
    display = img.copy()
    display.thumbnail((DISPLAY_EDGE, DISPLAY_EDGE))
    display.save(os.path.join(img_dir, out), 'JPEG', quality=85, optimize=True)
    thumb = img.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE))
    thumb.save(os.path.join(img_dir, out_t), 'JPEG', quality=80, optimize=True)
    return out, out_t


def build_public():
    """Regenerate the public bundle. Returns number of knives published."""
    con = db.connect()
    try:
        knives = db.list_knives(con)
    finally:
        con.close()
    dest = _public_dir()
    img_dir = os.path.join(dest, 'img')
    os.makedirs(dest, exist_ok=True)
    out = []
    for k in knives:
        row = {f: k.get(f) for f in _PUBLIC_FIELDS}
        # sale surface: a flag, plus asking price only while actively for sale
        row['for_sale'] = 1 if k.get('sale_status') in ('for_sale', 'pending') else 0
        if k.get('sale_status') == 'for_sale' and k.get('asking_price'):
            row['asking_price'] = k['asking_price']
        hero, thumb = _export_images(k, img_dir)
        row['img'], row['img_t'] = hero, thumb
        out.append(row)
    bundle = {
        'generated': datetime.now(timezone.utc).isoformat(),
        'count': len(out),
        'knives': out,
    }
    with open(os.path.join(dest, 'knives.json'), 'w') as f:
        json.dump(bundle, f, indent=1)
    return len(out)
