"""Build a source-only archive using an allowlist; never include local credentials/state."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('backend', 'frontend', 'infra', 'tools', 'submission', '.github', 'docs')
SKIP = {'node_modules', '.next', '.vercel', '__pycache__', '.pytest_cache', '.ruff_cache', 'cdk.out', 'cdk.connected.out', 'cdk.hosted.out'}
ROOT_FILES = ('README.md', 'LICENSE', 'VERIFICATION.md', 'MARKETPLACE_DEPLOYMENT.md',
              'pyproject.toml', '.gitignore', '.gitattributes', '.vercelignore', '.env.example', 'start_demo.sh', 'start_demo.ps1')


def main():
    files = [ROOT / name for name in ROOT_FILES]
    for directory in DIRECTORIES:
        for path in (ROOT / directory).rglob('*'):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(part in SKIP or part.startswith('.data') for part in relative.parts):
                continue
            if (path.name.startswith(('.env', 'PRIVATE')) and path.name != '.env.example') or path.suffix in {'.log', '.pyc', '.tsbuildinfo'}:
                continue
            files.append(path)
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    archive = output / 'PulseContinuum-source.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            bundle.write(path, path.relative_to(ROOT).as_posix())
    manifest = {'archive': archive.name, 'files': len(files),
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
