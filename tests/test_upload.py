# tests/test_upload.py — photo uploader (originals-preserving)
import io
import os

import pytest
from PIL import Image


TOKEN = 'crk-test-token'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('BLADEBOOK_DATA_DIR', str(tmp_path / 'crk'))
    monkeypatch.setenv('BLADEBOOK_ADMIN_TOKEN', TOKEN)
    from flask import Flask
    from bladebook.routes import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app.test_client()


def _h(tok=TOKEN):
    return {'X-Bladebook-Token': tok}


def _jpeg_bytes(w=1200, h=900):
    buf = io.BytesIO()
    Image.new('RGB', (w, h), (40, 40, 120)).save(buf, format='JPEG')
    return buf.getvalue()


def _upload(client, tag, files, tok=TOKEN):
    data = {'tag': tag}
    data['photos'] = [(io.BytesIO(b), name) for b, name in files]
    return client.post('/api/bladebook/upload', data=data, headers=_h(tok),
                       content_type='multipart/form-data')


def test_upload_requires_token(client):
    r = _upload(client, 'K01', [(_jpeg_bytes(), 'a.jpg')], tok='wrong')
    assert r.status_code == 401
    assert client.get('/api/bladebook/tags').status_code == 401


def test_upload_preserves_original_bytes(client, tmp_path):
    raw = _jpeg_bytes()
    r = _upload(client, 'K01', [(raw, 'IMG_0001.JPG')])
    assert r.status_code == 200
    saved = r.get_json()['saved']
    assert saved == ['001.jpg']
    on_disk = (tmp_path / 'crk' / 'originals' / 'K01' / '001.jpg').read_bytes()
    assert on_disk == raw          # byte-for-byte: originals are never re-encoded


def test_upload_makes_thumb_for_decodable_images(client, tmp_path):
    _upload(client, 'K01', [(_jpeg_bytes(3000, 2000), 'a.jpg')])
    thumb = tmp_path / 'crk' / 'thumbs' / 'K01' / '001.jpg'
    assert thumb.exists()
    assert max(Image.open(thumb).size) <= 400


def test_upload_keeps_undecodable_original_without_thumb(client, tmp_path):
    fake_heic = b'\x00\x00\x00\x18ftypheic' + b'\x01' * 64
    r = _upload(client, 'K02', [(fake_heic, 'IMG_0002.HEIC')])
    assert r.status_code == 200
    assert r.get_json()['saved'] == ['001.heic']
    on_disk = (tmp_path / 'crk' / 'originals' / 'K02' / '001.heic').read_bytes()
    assert on_disk == fake_heic
    assert not (tmp_path / 'crk' / 'thumbs' / 'K02' / '001.jpg').exists()


def test_upload_multiple_files_increment(client, tmp_path):
    r = _upload(client, 'K03', [(_jpeg_bytes(), 'a.jpg'), (_jpeg_bytes(), 'b.jpg')])
    assert r.get_json()['saved'] == ['001.jpg', '002.jpg']
    r2 = _upload(client, 'K03', [(_jpeg_bytes(), 'c.jpg')])
    assert r2.get_json()['saved'] == ['003.jpg']
    assert r2.get_json()['count'] == 3


def test_tag_normalized_and_validated(client, tmp_path):
    r = _upload(client, 'k7', [(_jpeg_bytes(), 'a.jpg')])
    assert r.status_code == 200
    assert r.get_json()['tag'] == 'K07'
    assert (tmp_path / 'crk' / 'originals' / 'K07' / '001.jpg').exists()
    for bad in ('', 'X01', 'K', '7', 'K1234', '../etc'):
        assert _upload(client, bad, [(_jpeg_bytes(), 'a.jpg')]).status_code == 400


def test_unknown_extension_falls_back_to_bin(client, tmp_path):
    r = _upload(client, 'K04', [(b'mystery-bytes', 'weird.xyz')])
    assert r.get_json()['saved'] == ['001.bin']


def test_oversize_rejected(client):
    big = b'\x00' * (30 * 1024 * 1024 + 1)
    r = _upload(client, 'K05', [(big, 'huge.jpg')])
    assert r.status_code == 400


def test_tags_endpoint_counts(client):
    _upload(client, 'K01', [(_jpeg_bytes(), 'a.jpg'), (_jpeg_bytes(), 'b.jpg')])
    _upload(client, 'K02', [(_jpeg_bytes(), 'c.jpg')])
    r = client.get('/api/bladebook/tags', headers=_h())
    assert r.status_code == 200
    assert r.get_json() == {'K01': 2, 'K02': 1}


def test_thumb_served_authed(client):
    _upload(client, 'K01', [(_jpeg_bytes(), 'a.jpg')])
    assert client.get('/api/bladebook/thumb/K01/001.jpg', headers=_h()).status_code == 200
    assert client.get('/api/bladebook/thumb/K01/001.jpg').status_code == 401
    assert client.get('/api/bladebook/thumb/K01/../001.jpg', headers=_h()).status_code in (400, 404)


def test_photos_listing_names(client):
    _upload(client, 'K08', [(_jpeg_bytes(), 'a.jpg'), (b'\x00\x00\x00\x18ftypheic' + b'\x01' * 64, 'b.HEIC')])
    r = client.get('/api/bladebook/photos/K08', headers=_h())
    assert r.get_json() == ['001.jpg', '002.heic']
    assert client.get('/api/bladebook/photos/K08').status_code == 401


def test_delete_photo_removes_original_and_thumb(client, tmp_path):
    _upload(client, 'K09', [(_jpeg_bytes(), 'a.jpg'), (_jpeg_bytes(), 'b.jpg')])
    r = client.delete('/api/bladebook/photo/K09/001.jpg', headers=_h())
    assert r.status_code == 200
    assert not (tmp_path / 'crk' / 'originals' / 'K09' / '001.jpg').exists()
    assert not (tmp_path / 'crk' / 'thumbs' / 'K09' / '001.jpg').exists()
    assert client.get('/api/bladebook/photos/K09', headers=_h()).get_json() == ['002.jpg']
    # names are never reused: next upload continues after the highest ever
    r2 = _upload(client, 'K09', [(_jpeg_bytes(), 'c.jpg')])
    assert r2.get_json()['saved'] == ['003.jpg']
    assert client.delete('/api/bladebook/photo/K09/001.jpg', headers=_h()).status_code == 404
    assert client.delete('/api/bladebook/photo/K09/../001.jpg', headers=_h()).status_code in (400, 404)
    assert client.delete('/api/bladebook/photo/K09/002.jpg').status_code == 401


def test_deleted_highest_name_never_reissued(client, tmp_path):
    _upload(client, 'K10', [(_jpeg_bytes(), 'a.jpg')])
    client.delete('/api/bladebook/photo/K10/001.jpg', headers=_h())
    r = _upload(client, 'K10', [(_jpeg_bytes(), 'b.jpg')])
    assert r.get_json()['saved'] == ['002.jpg']
    assert r.get_json()['count'] == 1   # .seq marker not counted
