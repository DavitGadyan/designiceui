"""The MCP surface is hand-rolled, so the protocol itself needs covering."""

import io
import json

import pytest

from designice import mcp_server


def call(method, params=None, request_id=1):
    return mcp_server.handle({"jsonrpc": "2.0", "id": request_id,
                              "method": method, "params": params or {}})


def test_initialize_echoes_a_supported_protocol():
    result = call("initialize", {"protocolVersion": "2024-11-05"})["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "designice"
    assert "tools" in result["capabilities"]


def test_unknown_protocol_falls_back_to_default():
    result = call("initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert result["protocolVersion"] == mcp_server.DEFAULT_PROTOCOL


def test_notifications_get_no_response():
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_every_tool_has_a_usable_schema():
    tools = call("tools/list")["result"]["tools"]
    assert tools
    for tool in tools:
        assert tool["description"].strip()
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        for name in schema.get("required", []):
            assert name in schema["properties"], f"{tool['name']} requires undeclared {name}"


def test_unknown_tool_is_a_protocol_error():
    assert call("tools/call", {"name": "nope", "arguments": {}})["error"]["code"] == -32602


def test_tool_failure_is_reported_not_raised():
    # A failing tool must come back as an isError result; raising would kill the
    # server and the client would only see the pipe close.
    response = call("tools/call", {"name": "design_get", "arguments": {"design": "nothing-like-this"}})
    assert response["result"]["isError"] is True
    assert "content" in response["result"]


def test_unknown_method_errors_with_an_id():
    assert call("made/up")["error"]["code"] == -32601


def test_serve_reads_and_writes_line_delimited_json():
    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n"
    )
    stdout = io.StringIO()
    mcp_server.serve(stdin, stdout)
    lines = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
    # Two requests, one notification -> exactly two responses.
    assert [m["id"] for m in lines] == [1, 2]


def test_bad_json_does_not_kill_the_loop():
    stdin = io.StringIO("{not json\n"
                        + json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\n")
    stdout = io.StringIO()
    mcp_server.serve(stdin, stdout)
    ids = [json.loads(l).get("id") for l in stdout.getvalue().splitlines() if l.strip()]
    assert 7 in ids
