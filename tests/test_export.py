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


def test_export_writes_permalink_pages(env, tmp_path):
    # a stale page from a previous publish must not survive regeneration
    stale = tmp_path / 'public' / 'k' / 'K99'
    stale.mkdir(parents=True)
    (stale / 'index.html').write_text('old')

    env.build_public()
    page1 = tmp_path / 'public' / 'k' / 'K01' / 'index.html'
    page2 = tmp_path / 'public' / 'k' / 'K02' / 'index.html'
    assert page1.exists() and page2.exists()
    assert not (tmp_path / 'public' / 'k' / 'K99').exists()

    h1 = page1.read_text()
    h2 = page2.read_text()

    # identity, specs, and the way back to the index
    assert 'Large Sebenza 21' in h1
    assert 'koa' in h1
    assert '../../#K01' in h1
    assert 'og:title' in h1

    # nothing private can ever reach a permalink page
    for banned in ('450', 'Example Cutlery', 'safe', 'secret', 'reconcile'):
        assert banned not in h1, banned

    # asking price shows only on the actively for-sale knife
    assert '800' in h2 and 'TRADE/SALE' in h2
    assert '999' not in h1 and 'TRADE/SALE' not in h1

    # no hero photo -> page still renders, without an <img>
    assert '<img' not in h2


def test_permalink_og_image_needs_base_url(env, tmp_path, monkeypatch):
    # without a configured public base URL there is no absolute og:image
    env.build_public()
    h1 = (tmp_path / 'public' / 'k' / 'K01' / 'index.html').read_text()
    assert 'og:image' not in h1

    monkeypatch.setenv('BLADEBOOK_PUBLIC_BASE_URL', 'https://example.com/pub')
    env.build_public()
    h1 = (tmp_path / 'public' / 'k' / 'K01' / 'index.html').read_text()
    assert '<meta property="og:image" content="https://example.com/pub/img/K01.jpg">' in h1
