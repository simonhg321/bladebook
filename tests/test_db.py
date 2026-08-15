# tests/test_db.py — data layer + knives API
import io

import pytest
from PIL import Image


TOKEN = 'crk-test-token'


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('BLADEBOOK_DATA_DIR', str(tmp_path / 'crk'))
    monkeypatch.setenv('BLADEBOOK_ADMIN_TOKEN', TOKEN)
    from bladebook import db
    return db


def _seed_one(db, con, tag='K01', **over):
    mid = db.upsert_model(con, 'Sebenza', 'Sebenza', '31', 'Large', 'Drop Point')
    fields = dict(model_id=mid, steel='MagnaCut', born_on='2025-03-03')
    fields.update(over)
    return db.upsert_knife(con, tag, **fields)


def test_upsert_model_dedupes(env):
    con = env.connect()
    a = env.upsert_model(con, 'Sebenza', 'Sebenza', '31', 'Large', 'Drop Point')
    b = env.upsert_model(con, 'Sebenza', 'Sebenza', '31', 'Large', 'Drop Point')
    c = env.upsert_model(con, 'Sebenza', 'Sebenza', 'Regular', 'Large', 'Drop Point')
    assert a == b and a != c


def test_upsert_knife_insert_then_update(env):
    con = env.connect()
    kid = _seed_one(env, con)
    kid2 = _seed_one(env, con, condition=1)
    assert kid == kid2
    k = env.list_knives(con)[0]
    assert k['condition'] == 1 and k['steel'] == 'MagnaCut'
    assert k['family'] == 'Sebenza' and k['generation'] == '31'


def test_upsert_knife_rejects_unknown_field(env):
    con = env.connect()
    with pytest.raises(ValueError):
        _seed_one(env, con, serial='nope')


def test_events_roundtrip(env):
    con = env.connect()
    kid = _seed_one(env, con)
    env.add_event(con, kid, '2026-08-13', 'photographed', detail='test batch')
    ev = env.list_events(con, kid)
    assert len(ev) == 1 and ev[0]['type'] == 'photographed'


def test_knives_api_joined_with_photos(env, tmp_path):
    con = env.connect()
    _seed_one(env, con, hero_photo='003.jpg')
    con.commit()
    con.close()
    from flask import Flask
    from bladebook.routes import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    buf = io.BytesIO()
    Image.new('RGB', (600, 400), (10, 10, 10)).save(buf, format='JPEG')
    client.post('/api/bladebook/upload', data={'tag': 'K01', 'photos': [(io.BytesIO(buf.getvalue()), 'a.jpg')]},
                headers={'X-Bladebook-Token': TOKEN}, content_type='multipart/form-data')
    assert client.get('/api/bladebook/knives').status_code == 401
    r = client.get('/api/bladebook/knives', headers={'X-Bladebook-Token': TOKEN})
    assert r.status_code == 200
    (k,) = r.get_json()
    assert k['tag'] == 'K01' and k['photos'] == ['001.jpg']
    assert k['hero_photo'] == '003.jpg' and k['family'] == 'Sebenza'
