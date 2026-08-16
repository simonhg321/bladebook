"""
bladebook/export.py — the public projection: private core, generated public
shell. build_public() writes a static bundle: knives.json (whitelisted
fields ONLY) + re-encoded, EXIF-stripped hero images. The public tier never
touches the DB — publishing is a deliberate regeneration step.
"""

import html as html_mod
import io
import json
import os
import shutil
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

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December']


def _fmt_born(d):
    if not d:
        return ''
    y, m, day = d.split('-')
    return f'{_MONTHS[int(m) - 1]} {int(day)}, {y}'


def _display_name(row):
    if row.get('family') == 'Sebenza':
        return ' '.join(x for x in (row.get('size'), 'Sebenza',
                                    row.get('generation')) if x)
    name = row.get('model') or row.get('family') or row['tag']
    if row.get('size') and row.get('size') not in name:
        return f"{row['size']} {name}"
    return name


def _page_html(row):
    """Standalone share page for one knife. Built ONLY from the whitelisted
    public row — private fields are structurally out of reach here. Set
    BLADEBOOK_PUBLIC_BASE_URL (the absolute URL your public dir is served
    at) to get og:image link previews in chats and social posts."""
    e = html_mod.escape
    base = os.environ.get('BLADEBOOK_PUBLIC_BASE_URL', '').rstrip('/')
    name = _display_name(row)
    title_bits = [name]
    if row.get('special_edition'):
        title_bits.append(row['special_edition'])
    title = e(' · '.join(title_bits))
    born = _fmt_born(row.get('born_on'))
    desc_bits = [b for b in (
        row.get('steel'),
        ' '.join(x for x in (row.get('damascus_smith'),
                             row.get('damascus_pattern')) if x) or None,
        row.get('inlay_material'),
        f'born {born}' if born else None) if b]
    desc = e(' · '.join(desc_bits) or 'From a private collection.')
    og_img = (f'<meta property="og:image" content="{base}/img/'
              f'{e(row["img"])}">\n' if base and row.get('img') else '')
    hero = (f'<img class="hero" src="../../img/{e(row["img"])}" '
            f'alt="{title}">\n' if row.get('img') else '')

    specs = []

    def spec(label, value):
        if value:
            specs.append(f'<tr><th>{e(label)}</th><td>{e(str(value))}</td></tr>')

    spec('Born on', born)
    spec('Blade', row.get('blade_shape'))
    spec('Steel', ' '.join(x for x in (row.get('steel'),
                                       row.get('hardness_note')) if x))
    spec('Damascus', ' '.join(x for x in (row.get('damascus_smith'),
                                          row.get('damascus_pattern')) if x))
    spec('Inlay / wood', ' — '.join(x for x in (row.get('inlay_material'),
                                                row.get('inlay_note')) if x))
    spec('Graphic / edition', row.get('graphic_name')
         or row.get('special_edition'))
    spec('Edition #', row.get('edition_number'))
    spec('Finish', row.get('surface_finish'))
    if row.get('hand') == 'left':
        spec('Hand', 'LEFT-HANDED')
    comes_with = ', '.join(lbl for f, lbl in (
        ('has_box', 'box'), ('has_card', 'card'), ('has_papers', 'papers'),
        ('has_pouch', 'pouch'), ('has_lanyard', 'lanyard')) if row.get(f))
    spec('Comes with', comes_with)
    sale = ''
    if row.get('for_sale'):
        price = (f" · ${row['asking_price']:g}"
                 if row.get('asking_price') else '')
        sale = f'<p class="sale">FOR TRADE/SALE{price}</p>\n'
    notes = (f'<p class="notes">{e(row["notes_public"])}</p>\n'
             if row.get('notes_public') else '')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title} — Collection</title>
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
{og_img}<meta property="og:type" content="website">
<style>
  :root {{ --cream:#faf6ee; --ink:#1a1a1a; --accent:#b8452c; --soft:#e8e0d0; }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ background:var(--cream); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         max-width:720px; margin:0 auto; padding:20px 16px 60px; line-height:1.5; }}
  h1 {{ font-size:1.5rem; margin:8px 0 2px; }}
  .tag {{ color:var(--accent); font-weight:800; letter-spacing:.08em; }}
  .edition {{ color:#666; margin-bottom:12px; }}
  img.hero {{ width:100%; border-radius:14px; border:2px solid var(--ink); margin:10px 0; }}
  table {{ border-collapse:collapse; width:100%; margin:14px 0; }}
  th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid var(--soft);
           vertical-align:top; }}
  th {{ width:150px; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase;
       color:#555; }}
  .sale {{ display:inline-block; background:var(--accent); color:#fff; font-weight:800;
          border-radius:10px; padding:6px 14px; margin:8px 0; }}
  .notes {{ background:#fff; border:2px solid var(--soft); border-radius:12px;
           padding:12px 14px; margin:12px 0; }}
  a.back {{ color:var(--accent); font-weight:700; }}
  footer {{ margin-top:26px; font-size:.75rem; color:#888; }}
</style>
</head>
<body>
  <p class="tag">{e(row['tag'])}</p>
  <h1>{title}</h1>
  <p class="edition">{desc}</p>
  {hero}{sale}<table>{''.join(specs)}</table>
  {notes}<p><a class="back" href="../../#{e(row['tag'])}">← the whole collection</a></p>
  <footer>From a private collection — not a store.</footer>
</body>
</html>
'''


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
    # per-knife permalink pages, regenerated from scratch (stale pages die)
    k_dir = os.path.join(dest, 'k')
    shutil.rmtree(k_dir, ignore_errors=True)
    for row in out:
        page_dir = os.path.join(k_dir, row['tag'])
        os.makedirs(page_dir)
        with open(os.path.join(page_dir, 'index.html'), 'w') as f:
            f.write(_page_html(row))
    bundle = {
        'generated': datetime.now(timezone.utc).isoformat(),
        'count': len(out),
        'knives': out,
    }
    with open(os.path.join(dest, 'knives.json'), 'w') as f:
        json.dump(bundle, f, indent=1)
    return len(out)
