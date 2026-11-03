"""Validate and promote an uploaded app bundle without a ChatGPT/CLI login."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen
import zipfile

MAX_BYTES = 100 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def version(value):
    require(isinstance(value, str) and re.fullmatch(r"\d+\.\d+\.\d+", value), "Invalid version")
    return tuple(map(int, value.split('.')))


def validate_feed(feed, repository):
    version(feed.get('version'))
    expected = f"https://raw.githubusercontent.com/{repository}/main/packages/WingDesk-app-{feed['version']}.zip"
    require(feed.get('schema') == 1 and feed.get('product') == 'wingdesk-source', 'Invalid app feed')
    require(feed.get('platform') == 'windows-x64' and feed.get('url') == expected, 'Wrong platform or package URL')
    require(type(feed.get('size')) is int and 0 < feed['size'] <= MAX_BYTES, 'Invalid package size')
    require(isinstance(feed.get('sha256'), str) and re.fullmatch(r'[a-f0-9]{64}', feed['sha256']), 'Invalid SHA-256')
    require(isinstance(feed.get('notes'), str) and 0 < len(feed['notes']) <= 4000, 'Missing release notes')


def validate_bundle(raw, feed):
    require(len(raw) == feed['size'], 'Package size mismatch')
    require(hashlib.sha256(raw).hexdigest() == feed['sha256'], 'Package SHA-256 mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        require(len(names) == len({name.casefold() for name in names}), 'Duplicate ZIP path')
        require(sum(item.file_size for item in entries) <= 200 * 1024 * 1024, 'Expanded package too large')
        for item in entries:
            name = item.filename
            path = PurePosixPath(name)
            require(name and not item.is_dir() and not path.is_absolute()
                    and not any(part in ('', '.', '..') for part in name.split('/'))
                    and not any(c in name for c in '\\:<>"|?*')
                    and not stat.S_ISLNK(item.external_attr >> 16), 'Unsafe ZIP path: ' + name)
            require(not name.startswith(('developer/', 'tests/'))
                    and path.suffix.lower() not in ('.db', '.sqlite3', '.dpapi', '.log', '.exe', '.ps1', '.pyc')
                    and path.name not in ('SOURCE-MANIFEST.json', '.env'), 'Private/development file in package: ' + name)
        require(archive.testzip() is None, 'ZIP CRC failure')
        manifest = json.loads(archive.read('BUNDLE-MANIFEST.json'))
        require(manifest.get('version') == feed['version'], 'Bundle version mismatch')
        require(manifest.get('launcher_minimum') == '2.0.1', 'Unsupported launcher requirement')
        hashes = manifest.get('files_sha256')
        require(isinstance(hashes, dict) and set(hashes) == set(names) - {'BUNDLE-MANIFEST.json'}, 'Bundle file inventory mismatch')
        require({'core.py', 'app.py', 'launch_app.py', 'ui/app.js', 'ui/index.html', 'PATCHNOTES.md'} <= set(hashes), 'Required app files missing')
        for name, digest in hashes.items():
            data = archive.read(name)
            require(hashlib.sha256(data).hexdigest() == digest, 'File SHA-256 mismatch: ' + name)
            if name.endswith('.py'):
                compile(data, name, 'exec')
        module = ast.parse(archive.read('core.py'))
        versions = [ast.literal_eval(node.value) for node in module.body
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets)]
        require(versions == [feed['version']], 'App version mismatch')
        patchnotes = archive.read('PATCHNOTES.md').decode('utf-8')
        require(feed['version'] in patchnotes, 'Unversioned patch notes')
        node = shutil.which('node')
        require(node, 'Node.js required for UI syntax validation')
        with tempfile.TemporaryDirectory(prefix='wingdesk-js-') as temporary:
            for index, name in enumerate(n for n in hashes if n.endswith('.js')):
                local = Path(temporary) / f'{index}.js'
                local.write_bytes(archive.read(name))
                subprocess.run([node, '--check', str(local)], check=True, capture_output=True, text=True)
    return patchnotes, len(hashes)


def validate(root, repository):
    current = json.loads((root / 'launcher-app.json').read_text(encoding='utf-8'))
    candidate_path = root / 'release-request.json'
    candidate = json.loads(candidate_path.read_text(encoding='utf-8')) if candidate_path.exists() else current
    validate_feed(current, repository)
    validate_feed(candidate, repository)
    require(version(candidate['version']) >= version(current['version']), 'Refusing downgrade')
    if candidate['version'] == current['version']:
        require(candidate == current, 'Published versions are immutable')
    # Preserve the previous working version before promoting the new one.
    validate_bundle((root / 'packages' / f"WingDesk-app-{current['version']}.zip").read_bytes(), current)
    notes, count = validate_bundle((root / 'packages' / f"WingDesk-app-{candidate['version']}.zip").read_bytes(), candidate)
    return current, candidate, notes, count


def promote(root, current, candidate, notes):
    if current == candidate:
        print(f"Version {candidate['version']} already published; verification only.")
        return False
    (root / 'launcher-app.json').write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / 'PATCHNOTES.md').write_text(notes, encoding='utf-8')
    notes_path = root / 'notes' / f"WingDesk-{candidate['version']}.md"
    require(not notes_path.exists() or notes_path.read_text(encoding='utf-8') == notes, 'Versioned patch notes already differ')
    notes_path.parent.mkdir(exist_ok=True)
    notes_path.write_text(notes, encoding='utf-8')
    readme_path = root / 'README.md'
    readme = readme_path.read_text(encoding='utf-8')
    readme = re.sub(r'현재 상품 관리 버전은 \d+\.\d+\.\d+입니다\.', f"현재 상품 관리 버전은 {candidate['version']}입니다.", readme)
    marker = '\n## ' + candidate['version'] + ' '
    if marker not in readme:
        section = (f"\n## {candidate['version']} 업데이트\n\n{candidate['notes']}\n\n"
                   f"런처 2.0.1 → 새 버전 다시 확인 → {candidate['version']} 업데이트하고 실행.\n\n"
                   f"[패치노트](notes/WingDesk-{candidate['version']}.md) · "
                   f"[앱 패키지](packages/WingDesk-app-{candidate['version']}.zip)\n")
        position = readme.find('\n## 1.')
        readme = readme[:position] + section + readme[position:] if position >= 0 else readme + section
    readme_path.write_text(readme, encoding='utf-8')
    return True


def verify_public(feed, repository, attempts=12):
    manifest_url = f'https://raw.githubusercontent.com/{repository}/main/launcher-app.json'
    last = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(manifest_url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'WingDesk-release-verifier'}), timeout=20) as response:
                public = json.load(response)
            require(public == feed, 'Public update manifest has not propagated')
            with urlopen(Request(feed['url'], headers={'User-Agent': 'WingDesk-release-verifier'}), timeout=30) as response:
                raw = response.read(MAX_BYTES + 1)
            validate_bundle(raw, feed)
            print('Unauthenticated public download, size, SHA-256 and bundle inventory verified.')
            return
        except Exception as error:
            last = error
            print(f'Public verification {attempt + 1}/{attempts}: {type(error).__name__}: {error}', flush=True)
            if attempt + 1 < attempts:
                time.sleep(5)
    raise RuntimeError('Public verification failed; do not report deployment complete') from last


def summary(message):
    print(message, flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as output:
            output.write(message + '\n\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', 'lookitoone/wingdesk-release'))
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--verify-public', action='store_true')
    args = parser.parse_args()
    try:
        current, candidate, notes, count = validate(args.root, args.repository)
        summary(f"Bundle validation passed: WingDesk {candidate['version']}, {count} verified files, {candidate['size']} bytes.")
        if args.publish and promote(args.root, current, candidate, notes):
            def git(*parts):
                return subprocess.run(['git', '-C', str(args.root), *parts], check=True, capture_output=True, text=True)
            git('config', 'user.name', 'github-actions[bot]')
            git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
            git('add', '--', 'launcher-app.json', 'PATCHNOTES.md', 'README.md', f"notes/WingDesk-{candidate['version']}.md")
            git('commit', '-m', f"Release WingDesk {candidate['version']} after bundle validation")
            # A normal fast-forward push fails safely if someone else moved main.
            git('push', 'origin', 'HEAD:refs/heads/main')
            summary('Update manifest and patch notes published together. Previous version retained.')
        if args.verify_public:
            verify_public(candidate, args.repository)
            summary(f"Deployment complete: WingDesk {candidate['version']}. Public download and launcher update manifest verified.")
    except Exception as error:
        summary(f'Deployment failed: {type(error).__name__}: {error}')
        raise


if __name__ == '__main__':
    main()
