import os


def test_app_serves_views_and_api(tmp_path, monkeypatch):
    monkeypatch.setenv('BLADEBOOK_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('BLADEBOOK_PUBLIC_DIR', str(tmp_path / 'public'))
    monkeypatch.setenv('BLADEBOOK_ADMIN_TOKEN', 't0k3n')
    os.makedirs(tmp_path / 'public', exist_ok=True)
    (tmp_path / 'public' / 'knives.json').write_text('{"knives": []}')
    from app import app
    c = app.test_client()
    assert c.get('/').status_code == 200                      # uploader html
    assert c.get('/catalog/').status_code == 200              # catalog html
    assert c.get('/public/knives.json').status_code == 200    # published bundle
    assert c.get('/api/bladebook/tags').status_code == 401    # API mounted, authed
    assert c.get('/api/bladebook/tags',
                 headers={'X-Bladebook-Token': 't0k3n'}).status_code == 200
