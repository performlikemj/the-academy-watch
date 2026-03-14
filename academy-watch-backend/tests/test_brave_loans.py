import json
import sys
from types import SimpleNamespace

from src.utils.brave_loans import collect_loans_from_brave


def test_collect_loans_from_brave_reads_output_array(monkeypatch):
    sample_results = [
        {
            'title': 'Speculation: John Doe temporary move',
            'snippet': 'Arsenal evaluating a potential loan arrangement for John Doe this season.',
            'url': 'https://goal.com/articles/john-doe-loan',
        }
    ]

    monkeypatch.setattr('src.utils.brave_loans.brave_search', lambda *args, **kwargs: sample_results)

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            data = {
                'relevant': True,
                'confidence': 0.35,
                'reason': 'test reason',
            }
            return SimpleNamespace(
                # output_text intentionally missing to ensure we iterate output
                output=[
                    SimpleNamespace(
                        content=[SimpleNamespace(text=json.dumps(data))]
                    )
                ]
            )

    fake_responses = FakeResponses()

    class FakeOpenAIClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = fake_responses

    fake_module = SimpleNamespace(OpenAI=lambda api_key: FakeOpenAIClient(api_key))
    monkeypatch.setitem(sys.modules, 'openai', fake_module)
    monkeypatch.setattr('src.utils.brave_loans.OpenAI', fake_module.OpenAI, raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')

    collection = collect_loans_from_brave('Arsenal', 2025)

    assert not collection.rows
    assert fake_responses.calls
    call = fake_responses.calls[0]
    assert 'response_format' in call
    assert call['response_format']['type'] == 'json_schema'


def test_collect_loans_from_brave_fetches_article_html_via_text(monkeypatch):
    sample_results = [
        {
            'title': 'Goal.com analysis: Loan roundup for Manchester United',
            'snippet': 'Manchester United exploring several loan moves this season.',
            'url': 'https://goal.com/articles/jane-smith-loan',
        }
    ]

    monkeypatch.setattr('src.utils.brave_loans.brave_search', lambda *args, **kwargs: sample_results)

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            schema = kwargs.get('response_format', {}).get('json_schema', {})
            name = schema.get('name')
            if name == 'loan_title_score':
                payload = {
                    'relevant': True,
                    'confidence': 0.9,
                    'reason': 'clear loan mention',
                }
            elif name == 'loan_rows':
                payload = {
                    'rows': [
                        {
                            'player_name': 'Jane Smith',
                            'loan_team': 'Arsenal',
                            'season_year': 2025,
                            'confidence': 0.8,
                            'evidence': 'Jane Smith joins Arsenal on loan',
                        }
                    ]
                }
            else:
                raise AssertionError(f"unexpected schema name: {name}")
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        content=[SimpleNamespace(text=json.dumps(payload))]
                    )
                ]
            )

    fake_responses = FakeResponses()

    class FakeOpenAIClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = fake_responses

    fake_module = SimpleNamespace(OpenAI=lambda api_key: FakeOpenAIClient(api_key))
    monkeypatch.setitem(sys.modules, 'openai', fake_module)
    monkeypatch.setattr('src.utils.brave_loans.OpenAI', fake_module.OpenAI, raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')

    class FakeResponse:
        def __init__(self, text):
            self.text = text
            self.status_code = 200

        def raise_for_status(self):
            return None

        def __getattr__(self, item):
            if item == 'output_text':
                raise AssertionError('should not read output_text from requests responses')
            raise AttributeError(item)

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.calls = []

        def get(self, url, timeout):
            self.calls.append((url, timeout))
            return FakeResponse('<html>Jane Smith joins Arsenal on loan.</html>')

    fake_session = FakeSession()

    def fake_session_factory():
        return fake_session

    import requests  # type: ignore

    monkeypatch.setattr(requests, 'Session', fake_session_factory)

    collection = collect_loans_from_brave('Manchester United', 2025)

    assert collection.rows
    assert fake_session.calls
    assert len(fake_responses.calls) == 2
