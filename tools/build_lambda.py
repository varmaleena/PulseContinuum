"""Package preinstalled Linux wheels and allowlisted application sources, never .env/state."""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    dependencies = ROOT / 'tmp/lambda-package'
    if not (dependencies / 'mangum').is_dir():
        raise RuntimeError('Install requirements-lambda.txt into tmp/lambda-package using Linux platform wheels first')
    output = ROOT / 'dist/backend-lambda.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in dependencies.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                archive.write(path, path.relative_to(dependencies).as_posix())
        for path in (ROOT / 'backend').rglob('*'):
            relative = path.relative_to(ROOT / 'backend')
            if any(part.startswith('.') or part in ('tests','__pycache__') for part in relative.parts):
                continue
            if path.is_file() and (path.suffix == '.py' or relative.parts[0] == 'sample_assets'):
                archive.write(path, relative.as_posix())
    with zipfile.ZipFile(output) as archive:
        size = sum(item.file_size for item in archive.infolist())
    if size > 250 * 1024 * 1024:
        raise RuntimeError('Lambda package exceeds uncompressed size limit')
    print(f'Lambda package: {output.stat().st_size // 1024**2} MiB zipped, {size // 1024**2} MiB expanded')
    print('SHA256:', hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
