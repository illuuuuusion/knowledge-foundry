"""AI-controlled local UI smoke; temporary configuration, no source requests or UAT."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    config = root / 'smoke.toml'
    config.write_text('[paths]\ndata_dir="data"\nsource_dir="sources"\noutput_dir="output"\n')
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith('KFORGE_'):
            del env[key]
    with (root / 'server.log').open('w+') as log:
        process = subprocess.Popen([sys.executable, '-m', 'kforge', '--config', str(config),
                                    'ui', '--port', str(port)], env=env, cwd=root,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    log.seek(0)
                    raise AssertionError('UI process exited: ' + log.read())
                try:
                    with urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
                        assert response.status == 200
                        assert response.read() == b'ok'
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError('UI health endpoint did not become available')
            assert not (root / 'data').exists()
            assert not (root / 'output').exists()
            print('Local Streamlit server: health HTTP 200/ok; no storage effects; no source access or UAT')
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
