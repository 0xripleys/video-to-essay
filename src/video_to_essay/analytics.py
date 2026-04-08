"""PostHog analytics helper for Python workers."""

import os

from posthog import Posthog

_client: Posthog | None = None


def get_posthog() -> Posthog | None:
    global _client
    api_key = os.environ.get("POSTHOG_API_KEY")
    if not api_key:
        return None
    if _client is None:
        _client = Posthog(
            project_api_key=api_key,
            host=os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com"),
        )
    return _client


def capture(event: str, properties: dict | None = None) -> None:
    """Capture a server-side event. Uses 'worker' as the distinct_id."""
    ph = get_posthog()
    if ph:
        ph.capture(event, distinct_id="worker", properties=properties or {})
