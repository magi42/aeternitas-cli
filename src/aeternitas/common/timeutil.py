from __future__ import annotations

import datetime as dt


def iso_date(d: dt.date) -> str:
    return d.isoformat()
