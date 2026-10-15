"""Build/install a wheel and check offline CLI commands in a temporary workspace.

Default: isolated dependencies, installed only from --wheelhouse (no network).
--reuse-dependencies: reuse this interpreter's site-packages via a .pth file;
the application itself is still freshly installed and its location is checked.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import tempfile
import venv
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    dependencies = parser.add_mutually_exclusive_group()
    dependencies.add_argument('--wheelhouse', type=Path, help='Directory containing dependency wheels')
    dependencies.add_argument('--reuse-dependencies', action='store_true',
                              help='Reuse current site-packages; this does not test dependency isolation')
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(('KFORGE_', 'PIP_')) and key not in ('PYTHONPATH', 'PYTHONHOME')}
    environment.update(PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_NO_CACHE_DIR='1')

    with tempfile.TemporaryDirectory(prefix='kforge-install-') as temporary:
        root = Path(temporary).resolve()

        def run(command, cwd=root):
            result = subprocess.run(list(map(str, command)), cwd=cwd, env=environment,
                                    capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise RuntimeError(f'Command failed ({result.returncode}): {command}\n'
                                   + result.stdout + result.stderr)
            return result.stdout

        wheels = root / 'wheels'
        run([sys.executable, '-m', 'pip', 'wheel', '--no-build-isolation', '--no-deps',
             '--wheel-dir', wheels, repository])
        wheel, = wheels.glob('knowledge_foundry-*.whl')
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if not (name.startswith('kforge/') or
                        re.fullmatch(r'knowledge_foundry-[^/]+\.dist-info', name.split('/')[0])):
                    raise AssertionError(f'Unexpected wheel content: {name}')
                if any(part in {'.env', 'data', 'sources', 'output', '.git'} for part in Path(name).parts):
                    raise AssertionError(f'Runtime or secret file in wheel: {name}')

        prefix = root / 'venv'
        venv.EnvBuilder(with_pip=True).create(prefix)
        python = prefix / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        cli = python.with_name('kforge.exe' if os.name == 'nt' else 'kforge')
        if args.reuse_dependencies:
            purelib = Path(run([python, '-c', 'import sysconfig; print(sysconfig.get_paths()["purelib"])']).strip())
            current_sites = sorted({sysconfig.get_paths()[key] for key in ('purelib', 'platlib')})
            (purelib / 'smoke_dependencies.pth').write_text('\n'.join(current_sites) + '\n', encoding='utf-8')
        install = [python, '-m', 'pip', 'install', '--no-index']
        if args.wheelhouse:
            install += ['--find-links', args.wheelhouse.resolve()]
        if args.reuse_dependencies:
            # The parent site's copy must neither satisfy this install nor be uninstalled.
            install += ['--no-deps', '--ignore-installed']
        run([*install, wheel])
        run([python, '-m', 'pip', 'check'])
        installed = Path(run([python, '-c', 'import kforge; print(kforge.__file__)']).strip()).resolve().parent
        if not installed.is_relative_to(prefix):
            raise AssertionError('Application import leaked from the original environment')
        sources = list((repository / 'src/kforge').rglob('*.py'))
        for source in sources:
            target = installed / source.relative_to(repository / 'src/kforge')
            if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
                raise AssertionError(f'Installed/source mismatch: {source.name}')

        config = root / 'runtime.toml'
        config.write_text('[paths]\ndata_dir="data"\nsource_dir="sources"\noutput_dir="output"\n')
        domain = root / 'domain.yaml'
        domain.write_bytes((repository / 'domain.example.yaml').read_bytes())
        commands = [('--help',), ('--version',), ('config',), ('init',),
                    ('export', '--format', 'jsonl', '--group-size', 'all'),
                    ('jobs', 'create', domain), ('consolidate', domain),
                    ('knowledge', domain, '--output', root / 'library')]
        for arguments in commands:
            run([cli, '--config', config, *arguments])
        if not (root / 'library/INDEX.md').is_file():
            raise AssertionError('Installed knowledge command produced no library index')
        print(json.dumps({'status': 'passed', 'commands': len(commands), 'package_files': len(sources),
                          'dependency_isolation': not args.reuse_dependencies,
                          'network': 'disabled for package installation; CLI uses an empty local store',
                          'user_acceptance': False}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, AssertionError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
