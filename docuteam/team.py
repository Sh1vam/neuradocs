# team.py -- shared helpers for multi-agent work (Chapter 05, Part F)
import json


def parse_json(text):
    """Parse the first JSON object in a model reply, tolerating text or code fences around it."""
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        raise ValueError('no JSON object in the reply')
    return json.loads(text[start:end + 1])      # json.JSONDecodeError is a ValueError
