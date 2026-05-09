import asyncio

import pytest

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from gateway.session import SessionSource, build_session_key


class RecoveryStubAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=True), Platform.TELEGRAM)
        self.sent: list[tuple[str, str]] = []

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    async def send(self, chat_id, content, reply_to=None, metadata=None, **kwargs) -> SendResult:
        self.sent.append((chat_id, content))
        return SendResult(success=True, message_id=f"sent-{len(self.sent)}")

    async def send_typing(self, chat_id, metadata=None) -> None:
        pass

    async def get_chat_info(self, chat_id):
        return {"name": "test", "type": "direct", "chat_id": chat_id}


def _event(text: str = "hello", *, update_id: int = 123) -> MessageEvent:
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(
            platform=Platform.TELEGRAM,
            chat_id="7712932768",
            chat_type="dm",
            user_id="7712932768",
            user_name="max",
        ),
        message_id="m1",
        platform_update_id=update_id,
    )


async def _drain(adapter: RecoveryStubAdapter) -> None:
    while True:
        tasks = list(adapter._background_tasks)
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_inbound_recovery_record_is_acked_after_success(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    adapter = RecoveryStubAdapter()

    async def handler(event):
        return "pong"

    adapter.set_message_handler(handler)
    await adapter.handle_message(_event())
    records = list((tmp_path / "gateway_pending" / "inbound").glob("telegram_*.json"))
    assert len(records) == 1

    await _drain(adapter)

    assert adapter.sent == [("7712932768", "pong")]
    assert list((tmp_path / "gateway_pending" / "inbound").glob("telegram_*.json")) == []


@pytest.mark.asyncio
async def test_replay_unacked_inbound_dispatches_saved_message(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    original = RecoveryStubAdapter()
    event = _event("recover me", update_id=456)
    session_key = build_session_key(event.source)
    recovery_id = original._journal_inbound_event(event, session_key)
    assert recovery_id

    adapter = RecoveryStubAdapter()
    seen = []

    async def handler(event):
        seen.append(event.text)
        return "recovered"

    adapter.set_message_handler(handler)
    replayed = await adapter.replay_unacked_inbound()
    assert replayed == 1

    await _drain(adapter)

    assert seen == ["recover me"]
    assert adapter.sent == [("7712932768", "recovered")]
    assert list((tmp_path / "gateway_pending" / "inbound").glob("telegram_*.json")) == []


@pytest.mark.asyncio
async def test_unacked_inbound_survives_send_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    class FailingSendAdapter(RecoveryStubAdapter):
        async def send(self, chat_id, content, reply_to=None, metadata=None, **kwargs) -> SendResult:
            self.sent.append((chat_id, content))
            return SendResult(success=False, error="httpx.ConnectError:", retryable=True)

    adapter = FailingSendAdapter()

    async def handler(event):
        return "pong"

    adapter.set_message_handler(handler)
    await adapter.handle_message(_event(update_id=789))
    await _drain(adapter)

    records = list((tmp_path / "gateway_pending" / "inbound").glob("telegram_*.json"))
    assert len(records) == 1
