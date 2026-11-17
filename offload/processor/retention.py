"""Delete old nights by age and by a disk budget."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path


def expired_dates(dates: list[str], today: datetime, keep_days: int) -> list[str]:
    if keep_days < 1:
        return []
    cutoff = (today - timedelta(days=keep_days)).strftime("%Y%m%d")
    return sorted(date for date in dates if date < cutoff)


def dates_over_budget(
    dates_oldest_first: list[str],
    sizes: dict[str, int],
    max_bytes: int,
) -> list[str]:
    """Drop oldest dates until the summed size is within max_bytes.

    max_bytes <= 0 disables the budget. The newest date is kept even if it
    alone is larger than the budget, so tonight is not deleted while it is running.
    """
    if max_bytes <= 0:
        return []
    ordered = list(dates_oldest_first)
    total = sum(sizes.get(date, 0) for date in ordered)
    victims: list[str] = []
    for date in ordered[:-1] if len(ordered) > 1 else []:
        if total <= max_bytes:
            break
        victims.append(date)
        total -= sizes.get(date, 0)
    return victims


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    if path.is_file():
        return path.stat().st_size
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total
