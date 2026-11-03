import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import release


def package(overrides=None):
    files = {'core.py': b"VERSION = '1.7.0'\n", 'app.py': b'pass\n',
             'launch_app.py': b'pass\n', 'ui/app.js': b'const ok = true;\n',
             'ui/index.html': b'<html></html>', 'PATCHNOTES.md': b'# WingDesk 1.7.0\n'}
    manifest = {'version': '1.7.0', 'launcher_minimum': '2.0.1',
                'files_sha256': {key: hashlib.sha256(value).hexdigest() for key, value in files.items()}}
    files['BUNDLE-MANIFEST.json'] = json.dumps(manifest).encode()
    files.update(overrides or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    raw = output.getvalue()
    feed = dict(schema=1, product='wingdesk-source', platform='windows-x64', version='1.7.0',
                url='https://raw.githubusercontent.com/lookitoone/wingdesk-release/main/packages/WingDesk-app-1.7.0.zip',
                size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), notes='Release notes')
    return raw, feed


class DeploymentTests(unittest.TestCase):
    def test_valid_bundle(self):
        raw, feed = package()
        self.assertEqual(release.validate_bundle(raw, feed)[1], 6)

    def test_corrupted_download(self):
        raw, feed = package()
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            release.validate_bundle(bytes([raw[0] ^ 1]) + raw[1:], feed)

    def test_changed_file_with_recomputed_archive_hash(self):
        raw, feed = package({'core.py': b"VERSION = '9.9.9'\n"})
        with self.assertRaisesRegex(ValueError, 'File SHA-256'):
            release.validate_bundle(raw, feed)

    def test_unlisted_file(self):
        raw, feed = package({'extra.txt': b'Unexpected'})
        with self.assertRaisesRegex(ValueError, 'inventory'):
            release.validate_bundle(raw, feed)

    def test_unsafe_path(self):
        raw, feed = package({'../outside.txt': b'Unexpected'})
        with self.assertRaisesRegex(ValueError, 'Unsafe ZIP path'):
            release.validate_bundle(raw, feed)

    def test_private_database(self):
        raw, feed = package({'user.sqlite3': b'private'})
        with self.assertRaisesRegex(ValueError, 'Private/development'):
            release.validate_bundle(raw, feed)

    def test_wrong_host(self):
        _, feed = package()
        feed['url'] = 'https://example.com/app.zip'
        with self.assertRaisesRegex(ValueError, 'package URL'):
            release.validate_feed(feed, 'lookitoone/wingdesk-release')

    def test_downgrade(self):
        _, feed = package()
        candidate = {**feed, 'version': '1.6.9', 'url': feed['url'].replace('1.7.0', '1.6.9')}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'launcher-app.json').write_text(json.dumps(feed))
            (root / 'release-request.json').write_text(json.dumps(candidate))
            with self.assertRaisesRegex(ValueError, 'downgrade'):
                release.validate(root, 'lookitoone/wingdesk-release')

    def test_rewriting_published_version(self):
        _, feed = package()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'launcher-app.json').write_text(json.dumps(feed))
            (root / 'release-request.json').write_text(json.dumps({**feed, 'notes': 'Changed'}))
            with self.assertRaisesRegex(ValueError, 'immutable'):
                release.validate(root, 'lookitoone/wingdesk-release')


if __name__ == '__main__':
    unittest.main()
