# check.py -- deterministic citation check (Chapter 05, Part I)
import re


def check_citations(answer, retrieved_ids):
    cited = set()
    for group in re.findall(r'\[([^\]]+)\]', answer):
        for part in re.split(r'[,;]', group):          # handles [1, 2] as well as [1][2]
            part = part.strip()
            if part:
                cited.add(part)
    return {'cited': sorted(cited), 'invalid': sorted(c for c in cited if c not in retrieved_ids)}
