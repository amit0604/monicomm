import pytest

from app.ai.llm_client import ExternalEndpointError, validate_llm_url


@pytest.mark.parametrize(
    "url",
    [
        "http://llm:11434",
        "http://localhost:11434",
        "http://10.0.5.20:8000",
        "http://192.168.1.10:11434",
        "https://gpu01.lan:8000",
    ],
)
def test_internal_urls_are_allowed(url):
    assert validate_llm_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://api.anthropic.com",
        "http://8.8.8.8:11434",
        "ftp://llm:21",
        "not a url",
    ],
)
def test_external_or_invalid_urls_are_refused(url):
    with pytest.raises(ExternalEndpointError):
        validate_llm_url(url)
