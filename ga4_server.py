"""Compatibility stub for the retired GA4 Measurement Protocol transport.

Website analytics is browser-only. Keeping a non-networking stub prevents old
imports or cached callers from creating a second client/session identity.
"""


def enqueue_ga4_event(measurement_id, api_secret, client_id, session_id, event_name, params):
    """Reject every legacy event without performing network I/O."""
    return False
