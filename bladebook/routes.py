"""
bladebook/routes.py — Flask blueprint for photo intake (M1 uploader).

Photos are keyed by permanent knife tag (K01..); everything else about a
knife attaches later at confirm time. All routes authed (X-Bladebook-Token
or ?key=, validated against BLADEBOOK_ADMIN_TOKEN):

  POST /api/bladebook/upload             multipart: tag=K07 + photos[] → archived originals
  GET  /api/bladebook/tags               {tag: photo_count} for the upload page
  GET  /api/bladebook/thumb/<tag>/<name> feedback thumbs for the upload page
"""

import hmac
import os
import re

from flask import Blueprint, jsonify, request, send_from_directory

from bladebook import photos

bp = Blueprint('bladebook', __name__)

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
_TAG_IN = re.compile(r'^K(\d{1,3})$')
_NAME = re.compile(r'^\d{3}\.[a-z0-9]+$')


def _data_dir():
    return os.environ.get('BLADEBOOK_DATA_DIR', os.path.join(os.getcwd(), 'data'))


def _orig_dir(tag):
    return os.path.join(_data_dir(), 'originals', tag)


def _thumb_dir(tag):
    return os.path.join(_data_dir(), 'thumbs', tag)


def _is_admin():
    token = os.environ.get('BLADEBOOK_ADMIN_TOKEN', '')
    if not token:
        return False
    provided = request.headers.get('X-Bladebook-Token') or request.args.get('key') or ''
    return hmac.compare_digest(provided, token)


def _admin_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **kw):
        if not _is_admin():
            return jsonify({'error': 'unauthorized'}), 401
        return fn(*a, **kw)
    return wrapper


def _norm_tag(raw):
    m = _TAG_IN.match((raw or '').strip().upper())
    if not m or len(m.group(1)) > 3:
        return None
    return f'K{int(m.group(1)):02d}'


@bp.route('/api/bladebook/upload', methods=['POST'])
@_admin_required
def upload():
    tag = _norm_tag(request.form.get('tag'))
    if not tag:
        return jsonify({'error': 'bad tag — use K01..K999'}), 400
    files = request.files.getlist('photos')
    if not files:
        return jsonify({'error': 'no photos'}), 400
    saved = []
    for f in files:
        data = f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            return jsonify({'error': f'{f.filename}: over 30MB cap',
                            'saved': saved}), 400
        name = photos.save_original(data, _orig_dir(tag), f.filename)
        photos.make_thumb(data, _thumb_dir(tag), name)
        saved.append(name)
    count = len(photos.list_photos(_orig_dir(tag)))
    return jsonify({'tag': tag, 'saved': saved, 'count': count})


@bp.route('/api/bladebook/tags', methods=['GET'])
@_admin_required
def tags():
    root = os.path.join(_data_dir(), 'originals')
    out = {}
    if os.path.isdir(root):
        for tag in sorted(os.listdir(root)):
            n = len(photos.list_photos(os.path.join(root, tag)))
            if n:
                out[tag] = n
    return jsonify(out)


@bp.route('/api/bladebook/photos/<tag>', methods=['GET'])
@_admin_required
def photos_list(tag):
    tag = _norm_tag(tag)
    if not tag:
        return jsonify({'error': 'bad tag'}), 400
    return jsonify(photos.list_photos(_orig_dir(tag)))


@bp.route('/api/bladebook/photo/<tag>/<name>', methods=['DELETE'])
@_admin_required
def photo_delete(tag, name):
    tag = _norm_tag(tag)
    if not tag or not _NAME.match(name):
        return jsonify({'error': 'bad path'}), 400
    if not photos.delete_photo(_orig_dir(tag), _thumb_dir(tag), name):
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True, 'deleted': name})


@bp.route('/api/bladebook/thumb/<tag>/<name>', methods=['GET'])
@_admin_required
def thumb(tag, name):
    tag = _norm_tag(tag)
    if not tag or not _NAME.match(name):
        return jsonify({'error': 'bad path'}), 400
    return send_from_directory(_thumb_dir(tag), name)


@bp.route('/api/bladebook/original/<tag>/<name>', methods=['GET'])
@_admin_required
def original(tag, name):
    tag = _norm_tag(tag)
    if not tag or not _NAME.match(name):
        return jsonify({'error': 'bad path'}), 400
    return send_from_directory(_orig_dir(tag), name)


@bp.route('/api/bladebook/knives', methods=['GET'])
@_admin_required
def knives_list():
    from bladebook import db
    con = db.connect()
    try:
        out = db.list_knives(con)
        for k in out:
            k['photos'] = photos.list_photos(_orig_dir(k['tag']))
            k['events'] = db.list_events(con, k['id'])
    finally:
        con.close()
    return jsonify(out)
