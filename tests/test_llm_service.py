from unittest.mock import MagicMock, patch

import pytest

from app.services.llm_service import (
    HAIKU, SONNET, system_block, extract_tool_input, _fetch_playbook_rules, _playbook_cache
)


def test_model_constants():
    assert HAIKU == "claude-haiku-4-5-20251001"
    assert SONNET == "claude-sonnet-4-6"


def test_system_block_has_cache_control():
    block = system_block("hello world")
    assert block["type"] == "text"
    assert block["text"] == "hello world"
    assert block["cache_control"] == {"type": "ephemeral"}


def test_extract_tool_input_found():
    block = MagicMock()
    block.type = "tool_use"
    block.name = "my_tool"
    block.input = {"key": "value"}

    resp = MagicMock()
    resp.content = [block]

    result = extract_tool_input(resp, "my_tool")
    assert result == {"key": "value"}


def test_extract_tool_input_not_found():
    block = MagicMock()
    block.type = "text"
    resp = MagicMock()
    resp.content = [block]

    assert extract_tool_input(resp, "missing_tool") is None


def test_extract_tool_input_wrong_name():
    block = MagicMock()
    block.type = "tool_use"
    block.name = "other_tool"
    block.input = {}
    resp = MagicMock()
    resp.content = [block]

    assert extract_tool_input(resp, "my_tool") is None


def test_call_claude_wraps_system_in_cache_block():
    with patch("app.services.llm_service._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock()

        from app.services.llm_service import call_claude
        call_claude(HAIKU, "System prompt", [{"role": "user", "content": "hello"}])

        call_args = mock_client.messages.create.call_args[1]
        system_arg = call_args["system"]
        assert isinstance(system_arg, list)
        assert system_arg[0]["cache_control"] == {"type": "ephemeral"}
        assert system_arg[0]["text"] == "System prompt"


def test_call_claude_passes_tools_when_provided():
    with patch("app.services.llm_service._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock()

        from app.services.llm_service import call_claude
        tools = [{"name": "my_tool", "description": "a tool", "input_schema": {"type": "object", "properties": {}}}]
        call_claude(HAIKU, "System", [{"role": "user", "content": "hi"}], tools=tools)

        call_args = mock_client.messages.create.call_args[1]
        assert "tools" in call_args
        assert call_args["tools"] == tools


def test_playbook_cache_uses_hash():
    _playbook_cache.clear()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"title": "Rule 1", "content": "Content A"},
    ]

    result1 = _fetch_playbook_rules(["cold"], cursor=mock_cur)
    result2 = _fetch_playbook_rules(["cold"], cursor=mock_cur)

    assert result1 == result2
    # DB should only be queried once (second call hits cache with same hash)
    assert mock_cur.execute.call_count == 2  # once per call (hash check each time)


def test_playbook_cache_invalidates_on_content_change():
    _playbook_cache.clear()
    mock_cur = MagicMock()
    mock_cur.fetchall.side_effect = [
        [{"title": "Rule 1", "content": "Version 1"}],
        [{"title": "Rule 1", "content": "Version 2"}],
    ]

    result1 = _fetch_playbook_rules(["cold"], cursor=mock_cur)
    result2 = _fetch_playbook_rules(["cold"], cursor=mock_cur)

    assert "Version 1" in result1
    assert "Version 2" in result2


def test_playbook_returns_empty_when_no_rules():
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    result = _fetch_playbook_rules(["nonexistent"], cursor=mock_cur)
    assert result == ""
