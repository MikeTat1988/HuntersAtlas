"""Build the player archive and separate corresponding-source archive.

The runtime base supplies unchanged, already validated native/generator binaries.
The launcher and installer are taken from the current verified frozen builds.
Game-derived maps, fonts, saves and user profiles are never packaging inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


VERSION = '1.0'
RUNTIME_BUILD = 'hunters-atlas-runtime-1.0'
EXAMPLE_IMAGES = (
    'quick-menu.png', 'great-bridge.png', 'tower-interiors.png',
    'cathedral-ward-map.png', 'clinic.png', 'dream.png', 'dlc.png',
    'menu-left-wrap.png',
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source_paths(repo: Path) -> list[Path]:
    result = subprocess.run(
        ['git', '-C', str(repo), 'ls-files', '-z', '--cached', '--others',
         '--exclude-standard', '--', 'source'],
        capture_output=True, check=True,
    )
    paths = {repo / item.decode('utf-8') for item in result.stdout.split(b'\0') if item}
    return sorted(path for path in paths if path.is_file())


def source_bundle(repo: Path, dependency_source: Path, destination: Path) -> None:
    inventory_path = repo / 'source' / 'META' / 'source-file-manifest.json'
    paths = source_paths(repo)
    inventory = {
        path.relative_to(repo / 'source').as_posix(): digest(path)
        for path in paths if path != inventory_path
    }
    inventory_path.write_text(json.dumps({'schema': 1, 'version': VERSION, 'files': inventory},
                                         indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as bundle:
        for path in paths:
            bundle.write(path, path.relative_to(repo / 'source').as_posix())
        with zipfile.ZipFile(dependency_source) as dependencies:
            for entry in dependencies.infolist():
                if entry.is_dir():
                    continue
                name = 'runtime-dependencies/' + entry.filename
                # Entries are read as data and never extracted or executed.
                with dependencies.open(entry) as src, bundle.open(name, 'w', force_zip64=True) as dst:
                    shutil.copyfileobj(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--runtime-base', type=Path, required=True)
    parser.add_argument('--dependency-source', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-output', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    work = args.work.resolve()
    if work.exists():
        raise RuntimeError('Packaging work folder must be new; existing files are preserved.')
    work.mkdir(parents=True)
    with zipfile.ZipFile(args.runtime_base) as base:
        manifest = json.loads(base.read('manifest.json'))
        for entry in base.infolist():
            name = entry.filename
            if entry.is_dir() or name.startswith(('docs/', 'examples/', 'adapter/', 'installer/', 'legal/', 'tools/')):
                continue
            if name in {'README.md', 'Install.ps1', 'Uninstall.ps1', 'manifest.json',
                        'source-receipt.json', 'installer-source-receipt.json'}:
                continue
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts or ':' in name:
                raise RuntimeError(f'Unsafe base archive path: {name}')
            destination = work / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with base.open(entry) as src, destination.open('wb') as dst:
                shutil.copyfileobj(src, dst)
    (work / 'maps').mkdir(exist_ok=True)
    for name in ('README.md', 'Install.cmd', 'Uninstall.cmd'):
        shutil.copy2(repo / name, work / name)
    (work / 'examples').mkdir()
    for name in EXAMPLE_IMAGES:
        shutil.copy2(repo / 'examples' / name, work / 'examples' / name)
    generator = repo / 'source' / 'generator' / 'dist' / 'generate_atlas'
    if not (generator / 'generate_atlas.exe').is_file():
        raise RuntimeError('Verified frozen map generator is missing.')
    shutil.copytree(generator, work / 'tools')
    build = repo / 'source' / 'launcher' / 'build'
    shutil.copytree(build / 'dist' / 'Bloodborne', work / 'adapter')
    shutil.copytree(build / 'installer-dist', work / 'installer')
    for name in ('Install.ps1', 'Uninstall.ps1'):
        shutil.copy2(repo / 'installer' / name, work / 'installer' / name)
    for name in ('source-receipt.json', 'installer-source-receipt.json'):
        shutil.copy2(build / name, work / name)
    (work / 'legal').mkdir()
    args.source_output.parent.mkdir(parents=True, exist_ok=True)
    if args.source_output.exists():
        raise RuntimeError('Refusing to overwrite an existing corresponding-source archive.')
    source_bundle(repo, args.dependency_source, args.source_output)
    (work / 'legal' / 'SOURCE.md').write_text(
        'Corresponding source for this binary release is available beside the player ZIP at '\
        'https://github.com/MikeTat1988/HuntersAtlas/releases/download/v1.0/'\
        'Hunters-Atlas-Source-1.0.zip. It includes the full implementation and dependency source.\n',
        encoding='utf-8')
    manifest['version'] = VERSION
    manifest['runtime_build'] = RUNTIME_BUILD
    files = sorted(path for path in work.rglob('*') if path.is_file())
    manifest['files'] = {
        path.relative_to(work).as_posix(): digest(path)
        for path in files if path.relative_to(work).as_posix() != 'settings/settings.ini'
    }
    (work / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    forbidden = [path.relative_to(work).as_posix() for path in work.rglob('*')
                 if any(label in path.name.casefold() for label in ('beta1', 'beta2'))
                 or path.name.casefold().startswith('hunters-atlas-1.4.')]
    if forbidden:
        raise RuntimeError(f'Obsolete release filenames: {forbidden}')
    readme = (work / 'README.md').read_text(encoding='utf-8')
    if 'beta' in readme.casefold() or '1.4.0' in readme:
        raise RuntimeError('Obsolete release label in README.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise RuntimeError('Refusing to overwrite an existing release archive.')
    with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        archive.writestr('maps/', b'')
        for path in sorted(work.rglob('*')):
            if not path.is_file():
                continue
            name = path.relative_to(work).as_posix()
            archive.write(path, name)
    print(json.dumps({'archive': str(args.output), 'version': VERSION,
                      'bytes': args.output.stat().st_size, 'sha256': digest(args.output),
                      'source_archive': str(args.source_output),
                      'source_bytes': args.source_output.stat().st_size,
                      'source_sha256': digest(args.source_output),
                      'immutable_files': len(manifest['files']),
                      'example_images': len(EXAMPLE_IMAGES)}, indent=2))


if __name__ == '__main__':
    main()
