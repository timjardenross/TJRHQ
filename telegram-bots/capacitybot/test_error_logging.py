"""The error backstop must carry a real traceback, and a dropped connection is a warning, not an error."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import httpx
from telegram.error import NetworkError, TimedOut

from telegram_bots.capacitybot import app


def _raise_and_capture(err: BaseException) -> BaseException:
    try:
        raise err
    except BaseException as caught:  # noqa: BLE001 - we want the traceback attached
        return caught


def _run(err, update=None):
    context = MagicMock(error=err)
    asyncio.run(app._on_error(update, context))


def test_network_errors_are_recognised():
    assert app._is_transient_network_error(httpx.ReadError("boom"))
    assert app._is_transient_network_error(NetworkError("down"))
    assert app._is_transient_network_error(TimedOut())
    assert not app._is_transient_network_error(ValueError("bad"))
    assert not app._is_transient_network_error(None)


def test_read_error_logs_a_warning_with_a_real_traceback(caplog):
    err = _raise_and_capture(httpx.ReadError("connection dropped"))
    with caplog.at_level(logging.DEBUG, logger=app.log.name):
        _run(err)
    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert record.exc_info and record.exc_info[1] is err and record.exc_info[2] is not None
    assert "ReadError" in record.getMessage()


def test_other_errors_stay_errors_and_name_the_callback(caplog):
    err = _raise_and_capture(ValueError("bad callback"))
    update = MagicMock(spec=app.Update)
    update.callback_query = MagicMock(data="cte|dt=s")
    update.message = None
    with caplog.at_level(logging.DEBUG, logger=app.log.name):
        _run(err, update)
    record = caplog.records[-1]
    assert record.levelno == logging.ERROR
    assert "cte|dt=s" in record.getMessage()
    assert record.exc_info[2] is not None
