---
name: python-cli
description: Use when asked for a command-line tool or script. argparse, a testable main(argv) and tests that never call the shell.
---
1. One module (tool.py) with main(argv=None): parse arguments with argparse and return an exit code. End the file with: if __name__ == "__main__": raise SystemExit(main()).
2. Keep the logic in small pure functions, separate from argument parsing and printing.
3. Tests import the functions and call main([...]) with the capsys fixture. Cover success, bad input (non-zero exit) and --help.
4. Standard library only unless the request names a package. README shows two example commands with their expected output.
