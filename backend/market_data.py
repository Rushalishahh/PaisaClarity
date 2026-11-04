import requests
from datetime import date, datetime

# Full-history endpoint of the benchmark fund (see get_scheme_nav_history).
MFAPI_BASE_URL = "https://api.mfapi.in/mf"


def get_mutual_fund_nav(scheme_code: str) -> float | None:
    """
    Fetches the latest NAV (Net Asset Value - the "price per unit" of a
    mutual fund) for a given AMFI scheme code, using the free mfapi.in API.

    Returns the NAV as a float, or None if anything goes wrong (invalid
    scheme code, the API is down, network issue, unexpected response
    shape, etc). Returning None instead of raising an exception means the
    caller can decide how to handle "we don't know the price right now"
    without a single failed price lookup crashing the whole request -
    e.g. if someone has 5 investments and 1 scheme code is wrong, we still
    want the other 4 to show up correctly.
    """
    url = f"https://api.mfapi.in/mf/{scheme_code}/latest"

    try:
        # timeout=5 is important: without it, a slow/hanging third-party
        # server would make YOUR endpoint hang indefinitely too, since
        # this is a synchronous call your request is waiting on.
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # raises an exception on 4xx/5xx responses

        payload = response.json()

        if payload.get("status") != "SUCCESS":
            return None

        nav_str = payload["data"][0]["nav"]  # e.g. "892.45600"
        return float(nav_str)

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        # requests.RequestException covers network errors, timeouts, and
        # the raise_for_status() call above. KeyError/IndexError cover the
        # API returning a shape we don't expect (e.g. empty "data" list).
        # ValueError covers the nav string not being a valid number.
        return None


def get_scheme_nav_history(scheme_code: str) -> list[tuple[date, float]] | None:
    """
    Fetch the FULL historical NAV series for a scheme via mfapi.in's
    /mf/{scheme_code} endpoint (no /latest suffix). Returns a list of
    (date, nav) pairs sorted oldest-first, or None if anything goes wrong
    (same defensive pattern as get_mutual_fund_nav: never raise, let the
    caller degrade gracefully).
    """
    url = f"{MFAPI_BASE_URL}/{scheme_code}"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        payload = response.json()

        if payload.get("status") != "SUCCESS":
            return None

        history: list[tuple[date, float]] = []
        for entry in payload.get("data", []):
            # Dates arrive as "18-09-2026" (DD-MM-YYYY) and NAVs as strings.
            nav_date = datetime.strptime(entry["date"], "%d-%m-%Y").date()
            history.append((nav_date, float(entry["nav"])))

        if not history:
            return None

        history.sort(key=lambda pair: pair[0])
        return history

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_nav_on_or_before(
    history: list[tuple[date, float]], target: date
) -> float | None:
    """
    Find the NAV for the nearest available date on or before `target`
    (weekends/holidays have no NAV). `history` must be sorted oldest-first.

    Uses binary search so a decades-long history is still O(log n) per lookup.
    Returns None only when the history starts AFTER the target date (fund
    didn't exist yet) - callers decide what to do with that.
    """
    low, high = 0, len(history) - 1
    best: tuple[date, float] | None = None

    while low <= high:
        mid = (low + high) // 2
        nav_date, nav = history[mid]
        if nav_date <= target:
            best = (nav_date, nav)
            low = mid + 1  # look for a closer date on the right
        else:
            high = mid - 1

    return best[1] if best else None