import json

import pytest
import structlog

from bot.config import LogConfig, LogRenderer
from bot.logging_config import get_processors
from bot.providers.errors import ProviderError


@pytest.mark.parametrize("renderer", [LogRenderer.JSON, LogRenderer.CONSOLE])
def test_exception_chain_is_rendered(renderer) -> None:
    config = LogConfig(
        project_name="test", show_datetime=False, datetime_format="iso",
        show_debug_logs=False, time_in_utc=True, use_colors_in_console=False,
        renderer=renderer, allow_third_party_logs=False,
    )
    output = structlog.testing.ReturnLogger()
    log = structlog.wrap_logger(
        output, processors=get_processors(config),
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )
    try:
        try:
            raise ConnectionError("connection lost")
        except ConnectionError as cause:
            raise ProviderError("provider failed", kind="network") from cause
    except ProviderError as exc:
        rendered = log.warning("provider_search_failed", exc_info=exc)

    if renderer == LogRenderer.JSON:
        event = json.loads(rendered)
        assert "exc_info" not in event
        rendered = event["exception"]
    assert "ConnectionError: connection lost" in rendered
    assert "ProviderError: provider failed" in rendered
    assert "Traceback" in rendered
