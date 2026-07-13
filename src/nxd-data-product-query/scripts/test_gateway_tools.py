"""Offline tests for the ``_open`` candidate-endpoint fall-through in
``gateway_tools.py``. No network access — ``McpClient.initialize`` is mocked
per candidate to raise or succeed.

Run:

    python3 -m unittest test_gateway_tools -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from gateway_tools import _open
from mcp_http import McpClient, McpError


def _fake_initialize(codes_by_endpoint: dict[str, int | None]):
    """Return a stand-in for ``McpClient.initialize`` keyed by ``self.endpoint``.

    ``None`` means "succeeds"; an int means "raise McpError(that code)".
    """

    def _init(self: McpClient) -> dict:
        code = codes_by_endpoint[self.endpoint]
        if code is not None:
            raise McpError(code, "boom", self.endpoint)
        return {}

    return _init


class OpenFallThroughTest(unittest.TestCase):
    def test_401_on_first_candidate_falls_through_to_second(self) -> None:
        endpoints = ["https://dp.example.com/mcp/", "https://api.example.com/dp/mcp/"]
        codes = {endpoints[0]: 401, endpoints[1]: None}
        with patch.object(McpClient, "initialize", _fake_initialize(codes)):
            c = _open(endpoints, token="nxdpat_x", timeout=1.0)
        self.assertEqual(c.endpoint, endpoints[1])

    def test_403_on_first_candidate_falls_through_to_second(self) -> None:
        endpoints = ["https://dp.example.com/mcp/", "https://api.example.com/dp/mcp/"]
        codes = {endpoints[0]: 403, endpoints[1]: None}
        with patch.object(McpClient, "initialize", _fake_initialize(codes)):
            c = _open(endpoints, token="nxdpat_x", timeout=1.0)
        self.assertEqual(c.endpoint, endpoints[1])

    def test_404_still_falls_through(self) -> None:
        endpoints = ["https://dp.example.com/mcp/", "https://api.example.com/dp/mcp/"]
        codes = {endpoints[0]: 404, endpoints[1]: None}
        with patch.object(McpClient, "initialize", _fake_initialize(codes)):
            c = _open(endpoints, token="nxdpat_x", timeout=1.0)
        self.assertEqual(c.endpoint, endpoints[1])

    def test_all_candidates_fail_reports_every_error(self) -> None:
        endpoints = ["https://dp.example.com/mcp/", "https://api.example.com/dp/mcp/"]
        codes = {endpoints[0]: 401, endpoints[1]: 404}
        with patch.object(McpClient, "initialize", _fake_initialize(codes)):
            with self.assertRaises(SystemExit) as ctx:
                _open(endpoints, token="nxdpat_x", timeout=1.0)
        message = str(ctx.exception)
        self.assertIn("MCP 401", message)
        self.assertIn("MCP 404", message)

    def test_non_auth_5xx_other_than_retryable_set_raises_immediately(self) -> None:
        # 500 is not in the fall-through allow-list (401/403/404/502/503/504) —
        # it should propagate instead of trying later candidates.
        endpoints = ["https://dp.example.com/mcp/", "https://api.example.com/dp/mcp/"]
        codes = {endpoints[0]: 500, endpoints[1]: None}
        with patch.object(McpClient, "initialize", _fake_initialize(codes)):
            with self.assertRaises(McpError) as ctx:
                _open(endpoints, token="nxdpat_x", timeout=1.0)
        self.assertEqual(ctx.exception.code, 500)


if __name__ == "__main__":
    unittest.main()
