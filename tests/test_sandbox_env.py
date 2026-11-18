"""The sandbox job gets exactly what Windows needs to start Python, and never one of your secrets."""
import importlib.util
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_runner():
    spec = importlib.util.spec_from_file_location('sandbox_runner', ROOT / 'runner' / 'server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_job_gets_systemroot_but_never_a_secret(monkeypatch, tmp_path):
    runner = load_runner()
    monkeypatch.setattr(runner, 'WORK', tmp_path / 'work')
    systemroot = os.environ.get('SYSTEMROOT', 'C:\\Windows')
    monkeypatch.setenv('SYSTEMROOT', systemroot)                      # on Windows, python.exe refuses to start without it
    monkeypatch.setenv('GROQ_API_KEY', 'gsk_must_not_leak')
    monkeypatch.setenv('SANDBOX_TOKEN', 'also_secret')
    show = 'import os\nprint(os.environ.get("SYSTEMROOT"), os.environ.get("GROQ_API_KEY"), os.environ.get("SANDBOX_TOKEN"))\n'
    rc, out = runner.run_job({'show.py': show}, ['python', 'show.py'], 30)
    assert rc == 0, out
    assert out.strip() == f'{systemroot} None None'
