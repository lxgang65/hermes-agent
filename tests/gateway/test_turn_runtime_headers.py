from gateway.run import GatewayRunner


def test_turn_runtime_preserves_default_headers():
    runner = object.__new__(GatewayRunner)
    runner._service_tier = None

    headers = {"User-Agent": "Mozilla/5.0"}
    route = runner._resolve_turn_agent_config(
        "hi",
        "gpt-5.5",
        {
            "api_key": "sk-test",
            "base_url": "https://www.10veai.cc",
            "provider": "custom",
            "api_mode": "codex_responses",
            "default_headers": headers,
        },
    )

    assert route["runtime"]["default_headers"] == headers


def test_agent_config_signature_changes_when_default_headers_change():
    base_runtime = {
        "api_key": "sk-test",
        "base_url": "https://www.10veai.cc",
        "provider": "custom",
        "api_mode": "codex_responses",
    }

    first = GatewayRunner._agent_config_signature(
        "gpt-5.5",
        {**base_runtime, "default_headers": {"User-Agent": "Mozilla/5.0"}},
        ["terminal"],
        "",
    )
    second = GatewayRunner._agent_config_signature(
        "gpt-5.5",
        {**base_runtime, "default_headers": {"User-Agent": "OpenAI/Python"}},
        ["terminal"],
        "",
    )

    assert first != second
