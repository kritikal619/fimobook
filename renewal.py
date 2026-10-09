"""Korea-time renewal scheduling shared by the interest API and tests."""
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
HOURS = {0: (0, 2, 8, 10, 12, 14, 16, 18, 20, 22),
         1: (1, 7, 9, 11, 13, 15, 17, 19, 21, 23)}


def renewal_is_quiet(preference, now):
    if preference is None or not preference.enabled:
        return False
    local = now.replace(tzinfo=timezone.utc).astimezone(KST) if now.tzinfo is None else now.astimezone(KST)
    minute = local.hour * 60 + local.minute
    start, end = preference.start_minute, preference.end_minute
    return start <= minute < end if start < end else minute >= start or minute < end


def renewal_reminder(card, now):
    target, _ = renewal_occurrences(card, now + timedelta(seconds=60))
    return target if target - timedelta(seconds=60) <= now < target else None


def renewal_occurrences(card, now=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(KST)
    candidates = []
    for offset in (-1, 0, 1):
        day = local + timedelta(days=offset)
        for hour in HOURS[int(card['eo'])]:
            candidates.append(day.replace(hour=hour, minute=int(card['min']),
                                          second=int(card.get('sec', 0)), microsecond=0))
    previous = max(value for value in candidates if value <= local)
    upcoming = min(value for value in candidates if value > local)
    return previous.astimezone(timezone.utc), upcoming.astimezone(timezone.utc)
