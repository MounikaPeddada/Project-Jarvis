import re
from tools.time_tools import get_time, get_date

TIME_RE = re.compile(r"\b(what('?s| is) the time|what time is it|time now|current time|tell me the (time|clock))\b")
DATE_RE = re.compile(r"\b(what('?s| is) (the |today'?s )?date|today'?s date|what day is (it|today))\b")


def route(text: str):
    """Return a reply if a local rule can handle the command, else None."""
    t = text.lower().strip()
    if TIME_RE.search(t):
        return f"It's {get_time()}, ma'am."
    if DATE_RE.search(t):
        return f"Today is {get_date()}, ma'am."
    return None