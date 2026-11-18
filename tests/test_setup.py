import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import setup_env  # noqa: E402


def test_setup_adds_what_is_missing_and_never_changes_what_you_set(tmp_path):
    env = tmp_path / '.env'
    env.write_text('GROQ_API_KEY=abc\nLLM_BIG=my/model\nAPP_PASSWORD=\n# a comment\n', encoding='utf-8')
    added = setup_env.ensure(env)
    values = setup_env.parse(env.read_text(encoding='utf-8'))
    assert values['GROQ_API_KEY'] == 'abc' and values['LLM_BIG'] == 'my/model'      # yours stay as they were
    assert values['APP_PASSWORD'] and values['SANDBOX_TOKEN'] and values['APP_PORT'] == '8001'
    assert set(added) == {'APP_PASSWORD', 'SANDBOX_TOKEN', 'APP_PORT'}               # an empty "APP_PASSWORD=" counts as missing
    assert '# a comment' in env.read_text(encoding='utf-8') and env.read_text(encoding='utf-8').count('APP_PASSWORD=') == 1
    assert setup_env.ensure(env) == {}                                               # a second run changes nothing


def test_setup_does_not_invent_the_api_key_and_can_turn_on_internet(tmp_path):
    env = tmp_path / '.env'
    added = setup_env.ensure(env, internet=True)
    assert added['GROQ_API_KEY'] is None and 'GROQ_API_KEY' not in setup_env.parse(env.read_text(encoding='utf-8'))
    values = setup_env.parse(env.read_text(encoding='utf-8'))
    assert values['SANDBOX_PROXY'] == 'http://egress:3128' and values['SANDBOX_INSTALL'] == '1'


def test_setup_flags_values_that_break_docker_compose(tmp_path):
    env = tmp_path / '.env'
    env.write_text('DOMAIN=chat.example.com   (for HTTPS: docker compose --profile tls up -d)\nAPP_PORT=80x\nLLM_BIG=openai/gpt-oss-120b\n', encoding='utf-8')
    found = setup_env.problems(setup_env.parse(env.read_text(encoding='utf-8')))
    assert any('DOMAIN' in f for f in found) and any('APP_PORT' in f for f in found) and not any('LLM_BIG' in f for f in found)


USER_ENV = """# Optional overrides:
LLM_BIG=openai/gpt-oss-120b
SANDBOX_TOKEN=abc123
HF_MODELS=Qwen/Qwen3-32B,meta-llama/Llama-3.3-70B-Instruct
LLM_EFFORT=high
APP_PASSWORD=pass
APP_PORT=8010
HOST=127.0.0.1
PORT=8001
SANDBOX_PROXY=http://egress:3128      then: docker compose --profile internet up -d
EGRESS_ALLOW=pypi.org,github.com,huggingface.co,   (the only domains the sandbox may reach)
SANDBOX_INSTALL=1                     the tester runs pip install -r requirements.txt before pytest
SANDBOX_NETWORK=bridge                  local Docker mode only
EGRESS_ALLOW=pypi.org,files.pythonhosted.org,github.com  
SKILLS_DIR=D:/Hackathon/myenv/LLM & RAG/Projects/neuradocs/skills                   where your own skills live
DOMAIN=localhost                 the domain for Caddy TLS (optional, see README)
BUILD_TEAM=10
WEB_CONCURRENCY=10
GITHUB_TOKEN=
"""


def test_fix_cleans_a_real_env_without_touching_secrets():
    cleaned, changes = setup_env.clean(USER_ENV)
    v = setup_env.parse(cleaned)
    assert v['SANDBOX_PROXY'] == 'http://egress:3128' and v['SANDBOX_INSTALL'] == '1' and v['DOMAIN'] == 'localhost'
    assert v['SKILLS_DIR'] == 'D:/Hackathon/myenv/LLM & RAG/Projects/neuradocs/skills' and v['BUILD_TEAM'] == '1'
    assert v['EGRESS_ALLOW'] == 'pypi.org,files.pythonhosted.org,github.com'          # the last one wins, as in docker
    assert cleaned.count('# (repeated: the last one wins)') == 1
    assert v['APP_PASSWORD'] == 'pass' and v['SANDBOX_TOKEN'] == 'abc123'            # secrets are never changed
    assert setup_env.clean(cleaned)[1] == []                                           # cleaning twice changes nothing


def test_advice_names_what_costs_you():
    tips = ' '.join(setup_env.advice(setup_env.parse(setup_env.clean(USER_ENV)[0])))        # advice runs after --fix
    for word in ('GROQ_API_KEY', 'HF_TOKEN', 'APP_PASSWORD is short', 'LLM_EFFORT=high', 'WEB_CONCURRENCY', 'SANDBOX_NETWORK=bridge', 'HOST and PORT', 'SKILLS_DIR'):
        assert word in tips, word


def test_problems_flags_text_after_a_value_before_the_fix():
    found = setup_env.problems(setup_env.parse(USER_ENV))
    assert any(f.startswith('SANDBOX_INSTALL') and '--fix' in f for f in found) and any(f.startswith('DOMAIN') for f in found)
    assert not any(f.startswith('APP_PASSWORD') for f in found)                      # secrets are not judged
