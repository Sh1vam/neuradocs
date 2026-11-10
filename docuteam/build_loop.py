# build_loop.py -- git checkpoints in the code folder (Chapter 07, Part G)
from safe_shell import run_command


def checkpoint(message):
    run_command(['git', 'add', '-A'])
    return run_command(['git', 'commit', '-m', message])      # ignored if there is nothing to commit
