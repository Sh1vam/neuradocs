#!/usr/bin/env python3
# ci_local.py -- the judge. The coder agent CANNOT edit this file or anything under tests/.
import subprocess
import sys

STEPS = [['ruff', 'check', '.'], ['python', '-m', 'pytest', '-q', '-x']]

def main():
    for step in STEPS:
        r = subprocess.run(step, check=False, capture_output=True, text=True)#r = subprocess.run(step, capture_output=True, text=True)
        print('$', ' '.join(step))
        print((r.stdout + r.stderr)[-1500:])
        if r.returncode != 0:
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
