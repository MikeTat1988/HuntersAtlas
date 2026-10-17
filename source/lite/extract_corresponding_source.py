"""Reconstruct an exact source tree from a deduplicated source release ZIP."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def extract(archive, recipe, destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as source:
        data=json.loads(source.read(recipe))
        for name,record in data['files'].items():
            path=PurePosixPath(name)
            if path.is_absolute() or '\\' in name or ':' in name or any(p in ('','.','..') for p in name.split('/')):
                raise ValueError('Unsafe source path')
            blob=source.read(record['member'])
            if hashlib.sha256(blob).hexdigest()!=record['sha256']:raise ValueError('Source hash mismatch: '+name)
            target=destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(blob)
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('recipe',help='corresponding-source/windows-v1.9-source.json, for example')
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    extract(args.archive,args.recipe,args.destination)
