---
name: write-skills
description: Use when asked to write, improve or save a skill, meaning a reusable set of instructions or a workflow. What makes a skill work: a precise description, short steps and concrete limits.
---
1. The description says WHEN to use the skill, in the words a user would use ("Use when asked to ..."), in one or two sentences. It is the only text always in the prompt, so it decides whether the skill is found.
2. The body is a numbered workflow of 5 to 10 steps in the imperative. Each step is something that can be checked.
3. Put concrete limits in: counts, sizes, names of tools and fields. "Keep it short" is not a rule; "at most 6 bullets of 90 characters" is.
4. Say what NOT to do for mistakes that really happened, not generic advice.
5. Stay under about 2,500 characters. If it needs more, split it into two skills with different descriptions.
6. Never put secrets, personal data or one-off facts into a skill: it is loaded into prompts.
7. Test it: run a real request that should trigger it and check that the result follows every step. Fix the step that was ignored.
8. Propose it with save_skill. The user approves it on the Skills page; until then nothing uses it.
