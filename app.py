#!/usr/bin/env python3
"""bladebook — run the whole thing: uploader, catalog, public index, API."""
import os

from flask import Flask, send_from_directory

from bladebook.routes import bp

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'html')
app = Flask(__name__)
app.register_blueprint(bp)


def _public_dir():
    return os.environ.get('BLADEBOOK_PUBLIC_DIR',
                          os.path.join(os.getcwd(), 'public'))


@app.route('/')
def uploader():
    return send_from_directory(HTML, 'index.html')


@app.route('/catalog/')
def catalog():
    return send_from_directory(os.path.join(HTML, 'catalog'), 'index.html')


@app.route('/public/')
def public_index():
    return send_from_directory(_public_dir(), 'index.html')


@app.route('/public/<path:name>')
def public_asset(name):
    return send_from_directory(_public_dir(), name)


if __name__ == '__main__':
    app.run(host=os.environ.get('BLADEBOOK_HOST', '127.0.0.1'),
            port=int(os.environ.get('BLADEBOOK_PORT', '5000')))
