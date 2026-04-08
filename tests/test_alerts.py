"""
Unit tests for alerts/telegram.py.
aiohttp is mocked — no network calls.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from alerts.telegram import TelegramAlert


TOKEN = "test_token_123"
CHAT_ID = "test_chat_456"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestTelegramAlert:
    def setup_method(self):
        self.alert = TelegramAlert(token=TOKEN, chat_id=CHAT_ID)

    # ── Constructor ───────────────────────────────────────────────────────────

    def test_base_url_built_from_token(self):
        assert self.alert._base == BASE_URL

    def test_token_and_chat_id_stored(self):
        assert self.alert.token == TOKEN
        assert self.alert.chat_id == CHAT_ID

    # ── Successful send ───────────────────────────────────────────────────────

    def test_send_posts_to_correct_url(self):
        mock_post = AsyncMock()
        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            run(self.alert.send("hello"))

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == BASE_URL

    def test_send_payload_contains_chat_id(self):
        mock_post = AsyncMock()
        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            run(self.alert.send("test message"))

        payload = mock_post.call_args[1]["json"]
        assert payload["chat_id"] == CHAT_ID

    def test_send_payload_contains_message_text(self):
        mock_post = AsyncMock()
        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            run(self.alert.send("BUY lot_123 @ $81.00"))

        payload = mock_post.call_args[1]["json"]
        assert payload["text"] == "BUY lot_123 @ $81.00"

    def test_send_payload_sets_html_parse_mode(self):
        mock_post = AsyncMock()
        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            run(self.alert.send("test"))

        payload = mock_post.call_args[1]["json"]
        assert payload["parse_mode"] == "HTML"

    # ── Event messages ────────────────────────────────────────────────────────

    @pytest.mark.parametrize("message", [
        "BUY lot_001 @ $81.00 (3.0864 SOL)",
        "SELL lot_001 @ $85.05 | PnL: $12.50",
        "TRAIL_STOP_HIT lot_001 @ $83.00 | PnL: $6.17",
        "PAUSED — breakout detected at $90.00",
        "HOLD lot_001 +5.2% — RSI 62 ADX 28",
    ])
    def test_send_accepts_all_event_message_types(self, message):
        mock_post = AsyncMock()
        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            run(self.alert.send(message))

        payload = mock_post.call_args[1]["json"]
        assert payload["text"] == message

    # ── Failure swallowing ────────────────────────────────────────────────────

    def test_send_does_not_raise_on_network_error(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("aiohttp.ClientSession", return_value=mock_session):
            # must not raise
            run(self.alert.send("test"))

    def test_send_does_not_raise_on_session_creation_error(self):
        with patch("aiohttp.ClientSession", side_effect=Exception("session error")):
            run(self.alert.send("test"))

    def test_send_returns_none(self):
        mock_post = AsyncMock()
        mock_session = AsyncMock()
        mock_session.post = mock_post
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = run(self.alert.send("test"))

        assert result is None
