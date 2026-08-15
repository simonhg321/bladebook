"""
bladebook/photos.py — originals-preserving photo intake for a knife collection.

The archive keeps uploaded bytes EXACTLY as received — full resolution,
original format, EXIF intact — under originals/<TAG>/NNN.<ext>. Thumbs are
best-effort derivatives for upload-page feedback only; a file PIL can't
decode (e.g. HEIC without pillow-heif) is archived anyway and just skips
its thumb. EXIF stripping happens at public-export time (see export.py),
never at intake.
"""

import os
import re

from PIL import Image, ImageOps, UnidentifiedImageError

THUMB_EDGE = 400
_ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'heic', 'heif', 'webp', 'tif', 'tiff', 'dng', 'gif'}
_NUM = re.compile(r'^(\d+)\.[a-z0-9]+$')


def _next_index(d):
    """Highest index ever issued + 1. A .seq marker survives deletions so a
    deleted name is never reissued (names act as stable photo IDs)."""
    n = 0
    seq = os.path.join(d, '.seq')
    try:
        n = int(open(seq).read())
    except (OSError, ValueError):
        pass
    for fn in os.listdir(d):
        m = _NUM.match(fn)
        if m:
            n = max(n, int(m.group(1)))
    with open(seq, 'w') as f:
        f.write(str(n + 1))
    return n + 1


def list_photos(d):
    """Stored photo names (NNN.ext) in order — ignores the .seq marker."""
    if not os.path.isdir(d):
        return []
    return sorted(fn for fn in os.listdir(d) if _NUM.match(fn))


def _ext_for(filename):
    ext = os.path.splitext(filename or '')[1].lstrip('.').lower()
    return ext if ext in _ALLOWED_EXT else 'bin'


def save_original(data, orig_dir, filename):
    """Archive raw bytes untouched; returns the stored name (NNN.ext)."""
    os.makedirs(orig_dir, exist_ok=True)
    name = f'{_next_index(orig_dir):03d}.{_ext_for(filename)}'
    with open(os.path.join(orig_dir, name), 'wb') as f:
        f.write(data)
    return name


def delete_photo(orig_dir, thumb_dir, name):
    """Remove one archived original and its thumb. Names are never reused."""
    removed = False
    p = os.path.join(orig_dir, name)
    if os.path.exists(p):
        os.unlink(p)
        removed = True
    t = os.path.join(thumb_dir, os.path.splitext(name)[0] + '.jpg')
    if os.path.exists(t):
        os.unlink(t)
    return removed


def make_thumb(data, thumb_dir, stored_name):
    """Best-effort ≤400px JPEG thumb; returns thumb name or None."""
    import io
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img = img.convert('RGB')
    except (UnidentifiedImageError, OSError):
        return None
    os.makedirs(thumb_dir, exist_ok=True)
    name = os.path.splitext(stored_name)[0] + '.jpg'
    img.thumbnail((THUMB_EDGE, THUMB_EDGE))
    img.save(os.path.join(thumb_dir, name), 'JPEG', quality=80, optimize=True)
    return name
