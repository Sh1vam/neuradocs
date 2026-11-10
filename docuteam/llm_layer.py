# llm_layer.py -- provider adapter (Chapter 05, Part B) with the DocuTeam changes.
# NO API KEYS IN THIS FILE. Keys are read from environment variables only.
import json
import os

from config import MODELS
from retry import with_retries

PROVIDERS = {
    'groq': {'kind': 'openai', 'model': MODELS['big'],
             'base_url': 'https://api.groq.com/openai/v1', 'key': 'GROQ_API_KEY',
             'effort': 'low', 'max_out': 3000},      # raised from 1200: file contents inside tool calls need room
    'local': {'kind': 'openai', 'model': 'YOUR_LOCAL_MODEL_TAG',
              'base_url': 'http://localhost:11434/v1', 'key': None},
    'claude': {'kind': 'anthropic', 'model': 'claude-sonnet-5-5'},
    'claude-fast': {'kind': 'anthropic', 'model': 'claude-haiku-5-5'},
}
PROVIDERS['groq-small'] = dict(PROVIDERS['groq'], model=MODELS['small'])

# Neutral transcript items:
#  {'role': 'user', 'text': str}
#  {'role': 'assistant', 'text': str, 'calls': [{'id', 'name', 'args'}]}
#  {'role': 'tool', 'id': str, 'name': str, 'result': str}


def to_anthropic(tr):
    out = []
    for m in tr:
        if m['role'] == 'user':
            out.append({'role': 'user', 'content': m['text']})
        elif m['role'] == 'assistant':
            blocks = [{'type': 'text', 'text': m['text']}] if m.get('text') else []
            for c in m.get('calls', []):
                blocks.append({'type': 'tool_use', 'id': c['id'], 'name': c['name'], 'input': c['args']})
            out.append({'role': 'assistant', 'content': blocks})
        else:
            block = {'type': 'tool_result', 'tool_use_id': m['id'], 'content': m['result']}
            if out and out[-1]['role'] == 'user' and isinstance(out[-1]['content'], list):
                out[-1]['content'].append(block)
            else:
                out.append({'role': 'user', 'content': [block]})
    return out


def to_openai(system, tr):
    out = [{'role': 'system', 'content': system}]
    for m in tr:
        if m['role'] == 'user':
            out.append({'role': 'user', 'content': m['text']})
        elif m['role'] == 'assistant':
            msg = {'role': 'assistant', 'content': m.get('text') or None}
            if m.get('calls'):
                msg['tool_calls'] = [{'id': c['id'], 'type': 'function',
                                      'function': {'name': c['name'], 'arguments': json.dumps(c['args'])}}
                                     for c in m['calls']]
            out.append(msg)
        else:
            out.append({'role': 'tool', 'tool_call_id': m['id'], 'content': m['result']})
    return out


def _args(raw):
    """Parse tool-call arguments without crashing the whole run on malformed JSON."""
    try:
        val = json.loads(raw or '{}')
    except json.JSONDecodeError:
        return {'_error': 'invalid JSON arguments'}
    return val if isinstance(val, dict) else {'_error': 'arguments were not a JSON object'}


def chat(provider, system, tr, tools=None, max_tokens=1500):
    cfg = PROVIDERS[provider]
    if cfg.get('key') and cfg['key'] not in os.environ:
        raise RuntimeError('Set the environment variable ' + cfg['key'] + ' (see SETUP.md)')

    if cfg['kind'] == 'anthropic':
        import anthropic                                   # imported only if you use Claude
        kw = {}
        if tools:
            kw['tools'] = [{'name': t['name'], 'description': t['description'],
                            'input_schema': t['schema']} for t in tools]
        r = with_retries(lambda: anthropic.Anthropic().messages.create(
            model=cfg['model'], max_tokens=max_tokens, system=system,
            messages=to_anthropic(tr), **kw))
        text = ''.join(b.text for b in r.content if b.type == 'text')
        calls = [{'id': b.id, 'name': b.name, 'args': b.input} for b in r.content if b.type == 'tool_use']
        return {'text': text, 'calls': calls, 'tokens': r.usage.input_tokens + r.usage.output_tokens}

    from openai import BadRequestError, OpenAI
    kw = {}
    if tools:
        kw['tools'] = [{'type': 'function', 'function': {'name': t['name'],
                        'description': t['description'], 'parameters': t['schema']}} for t in tools]
    if cfg.get('effort'):
        kw['extra_body'] = {'reasoning_effort': cfg['effort']}
    if cfg.get('max_out'):
        kw['max_completion_tokens'] = cfg['max_out']
    client = OpenAI(api_key=os.environ[cfg['key']] if cfg['key'] else 'not-needed',
                    base_url=cfg['base_url'])

    def create():
        return client.chat.completions.create(
            model=cfg['model'], messages=to_openai(system, tr), **kw)

    r = None
    for attempt in range(3):
        try:
            r = with_retries(create)
            break
        except BadRequestError as e:
            # Groq rejects malformed tool-call JSON; the model usually gets it right on a retry.
            if 'tool_use_failed' not in str(e) or attempt == 2:
                raise
    msg = r.choices[0].message
    calls = [{'id': tc.id, 'name': tc.function.name, 'args': _args(tc.function.arguments)}
             for tc in (msg.tool_calls or [])]
    tokens = r.usage.total_tokens if getattr(r, 'usage', None) else 0
    return {'text': msg.content or '', 'calls': calls, 'tokens': tokens}