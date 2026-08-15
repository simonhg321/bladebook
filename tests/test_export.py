# tests/test_export.py — the public projection must leak nothing private
import io
import json
import os

import pytest
from PIL import Image


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('BLADEBOOK_DATA_DIR', str(tmp_path / 'crk'))
    monkeypatch.setenv('BLADEBOOK_PUBLIC_DIR', str(tmp_path / 'public'))
    from bladebook import db, export
    con = db.connect()
    mid = db.upsert_model(con, 'Sebenza', 'Sebenza', '21', 'Large', 'Drop Point')
    db.upsert_knife(con, 'K01', model_id=mid, steel='S35VN',
                    born_on='2013-07-02', inlay_material='koa',
                    price_paid=450.0, acquired_from='Example Cutlery',
                    location='safe', notes_private='secret',
                    condition_note='reconcile me',
                    sale_status='keeping', asking_price=999.0,
                    hero_photo='001.jpg')
    db.upsert_knife(con, 'K02', model_id=mid, steel='S35VN',
                    sale_status='for_sale', asking_price=800.0)
    con.commit()
    con.close()
    # one real photo for K01, with EXIF that must not survive export
    d = tmp_path / 'crk' / 'originals' / 'K01'
    d.mkdir(parents=True)
    img = Image.new('RGB', (2400, 1800), (90, 60, 20))
    exif = Image.Exif()
    exif[0x010F] = 'Apple'          # Make tag — marker for EXIF survival
    img.save(d / '001.jpg', exif=exif)
    return export


def test_export_whitelists_and_strips(env, tmp_path):
    n = env.build_public()
    assert n == 2
    bundle = json.load(open(tmp_path / 'public' / 'knives.json'))
    assert bundle['count'] == 2
    k1 = next(k for k in bundle['knives'] if k['tag'] == 'K01')
    k2 = next(k for k in bundle['knives'] if k['tag'] == 'K02')

    # private fields absent entirely, not just null
    for banned in ('price_paid', 'acquired_from', 'location', 'notes_private',
                   'condition_note', 'sale_status', 'hero_photo', 'id',
                   'model_id', 'created', 'updated'):
        assert banned not in k1, banned

    # asking price only surfaces on an actively for-sale knife
    assert 'asking_price' not in k1
    assert k1['for_sale'] == 0
    assert k2['asking_price'] == 800.0 and k2['for_sale'] == 1

    # whitelisted data made it
    assert k1['inlay_material'] == 'koa' and k1['born_on'] == '2013-07-02'

    # images: re-encoded, resized, EXIF gone
    hero = tmp_path / 'public' / 'img' / 'K01.jpg'
    thumb = tmp_path / 'public' / 'img' / 'K01_t.jpg'
    assert hero.exists() and thumb.exists()
    out = Image.open(hero)
    assert max(out.size) <= 1600
    assert 0x010F not in out.getexif()
    assert k2['img'] is None    # no photos yet → no image, no crash
