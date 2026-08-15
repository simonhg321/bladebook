#!/usr/bin/env python3
"""Regenerate the public collection index (whitelisted static bundle)."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bladebook import export  # noqa: E402

n = export.build_public()
src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'html', 'public', 'index.html')
shutil.copy(src, os.path.join(export._public_dir(), 'index.html'))
print(f'published {n} knives to {export._public_dir()}')
