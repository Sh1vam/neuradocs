"""What a sandbox job is given: enough for Python and pytest to start on Windows, and never one of your secrets."""
import importlib.util
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_runner():
    spec = importlib.util.spec_from_file_location('sandbox_runner', ROOT / 'runner' / 'server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_job_gets_a_home_and_systemroot_but_never_a_secret(monkeypatch, tmp_path):
    runner = load_runner()
    monkeypatch.setattr(runner, 'WORK', tmp_path / 'work')
    systemroot = os.environ.get('SYSTEMROOT', 'C:\\Windows')
    monkeypatch.setenv('SYSTEMROOT', systemroot)                      # Windows' network layer (socket, asyncio) needs it
    monkeypatch.setenv('GROQ_API_KEY', 'gsk_must_not_leak')
    monkeypatch.setenv('SANDBOX_TOKEN', 'also_secret')
    show = ('import os\n'
            'home = os.environ.get("USERPROFILE")\n'                  # Windows' home: Path.home() raises without it, and some pytest plugins call it on import
            'print(os.environ.get("SYSTEMROOT"), os.environ.get("GROQ_API_KEY"), os.environ.get("SANDBOX_TOKEN"), '
            'home is not None and os.path.samefile(home, os.getcwd()))\n')
    rc, out = runner.run_job({'show.py': show}, ['python', 'show.py'], 30)
    assert rc == 0, out
    assert out.strip() == f'{systemroot} None None True', out         # home is the job's own folder, not yours


def test_a_pytest_job_starts_in_the_stripped_environment(monkeypatch, tmp_path):
    runner = load_runner()
    monkeypatch.setattr(runner, 'WORK', tmp_path / 'work')
    rc, out = runner.run_job({'test_ok.py': 'def test_ok():\n    assert 1 + 1 == 2\n'}, ['python', '-m', 'pytest', '-q'], 120)
    assert rc == 0 and '1 passed' in out, out                         # `out` is pytest's own words, so a failure explains itself
