# safe_shell.py -- command policy: allowlist, no shell strings (Chapter 07, Part F)
import subprocess
from pathlib import Path

from config import WORKSPACE

WORKSPACE = (WORKSPACE / 'code').resolve()      # host-side commands run only in the code folder
WORKSPACE.mkdir(exist_ok=True)

# The checkpoint repository lives OUTSIDE the code folder (workspace/.checkpoints.git), so workspace/code has no .git,
# .gitignore or .gitmodules and is never mistaken for a nested repository or a separate workspace.
GITDIR = WORKSPACE.parent / '.checkpoints.git'


def _git_prefix():
    if not GITDIR.exists():
        try:
            subprocess.run(['git', f'--git-dir={GITDIR}', f'--work-tree={WORKSPACE}', 'init', '-q'], cwd=WORKSPACE, capture_output=True)
            (GITDIR / 'info').mkdir(exist_ok=True)
            (GITDIR / 'info' / 'exclude').write_text('__pycache__/\n.pytest_cache/\n.ruff_cache/\n*.pyc\nbuilds/\n_snippets/\n')
        except FileNotFoundError:
            pass                                            # git is not installed: the command below reports it
    return [f'--git-dir={GITDIR}', f'--work-tree={WORKSPACE}', '-c', 'user.name=docuteam', '-c', 'user.email=docuteam@localhost']
ALLOWED = {'python', 'pytest', 'ruff', 'bandit', 'git'}
GIT_NEEDS_HUMAN = {'push', 'clean', 'reset', 'remote', 'config', 'rebase'}


def check_command(argv):
    if not argv:
        raise PermissionError('empty command')
    exe = Path(argv[0]).name.lower().removesuffix('.exe')
    if exe not in ALLOWED:
        raise PermissionError('command not allowed: ' + exe)
    if exe == 'git' and len(argv) > 1 and argv[1] in GIT_NEEDS_HUMAN:
        raise PermissionError('git ' + argv[1] + ' needs human approval')
    for a in argv[1:]:
        if a.startswith('-'):
            continue
        if '/' in a or '\\' in a or ':' in a:                 # looks like a path
            if not (WORKSPACE / a).resolve().is_relative_to(WORKSPACE):
                raise PermissionError('path outside workspace: ' + a)


def run_command(argv, timeout=60):
    check_command(argv)
    cmd = list(argv)
    if Path(cmd[0]).name.lower().removesuffix('.exe') == 'git':       # every git command works on the hidden repository
        cmd = [cmd[0]] + _git_prefix() + cmd[1:]
    try:
        r = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True,
                           timeout=timeout, shell=False)
    except FileNotFoundError:
        return 127, 'command not found: ' + argv[0]
    except subprocess.TimeoutExpired:
        return 124, 'timed out after ' + str(timeout) + ' seconds'
    return r.returncode, (r.stdout + r.stderr)[-4000:]
