---
name: bugfix-workflow
description: Use when asked to fix a bug, a failing test or an error. Reproduce first, change as little as possible, prove the fix with the tests.
---
1. Reproduce: run the failing test or command and read the error. If there is no test, write one that fails for the reported reason.
2. Find the cause, not the symptom: read the code path the traceback names before editing.
3. Make the smallest change that fixes the cause. Do not rewrite unrelated code, rename things, or weaken or delete tests.
4. Run the whole test suite, not just one test. A fix that breaks another test is not a fix.
5. Explain in three lines: what was wrong, what you changed, which tests prove it.
