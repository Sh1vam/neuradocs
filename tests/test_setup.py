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
