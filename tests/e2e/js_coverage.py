"""How much of the page's own JavaScript ran during a browser session.

Chrome counts a function as run when its own range was entered. Counting bytes
instead would flatter any suite: most of the page's 145k characters are the
one-time startup that every load runs, so a byte figure sits near 90 percent
however little of the page a suite presses.

Two things about how V8 reports coverage decide how this reads it.

The page's script is inline, and an inline script is reported with an empty url,
so the page's script is found by a token only it carries. And V8 may report one
script across several entries, so the entries are merged per scriptId first.
Without that merge the same script is counted twice and the totals drift between
runs of an unchanged page, which makes the number unusable as a target.

A function is keyed by where its own range starts, not by its name: most handlers
in this page are anonymous, and keying on the name would collapse all of them
into one entry.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PAGE_MARKERS = ("requestCancel", "renderStrip")


def start(page):
    """Begin precise coverage. Call it before the navigation, or startup is lost."""
    session = page.context.new_cdp_session(page)
    session.send("Debugger.enable")
    session.send("Profiler.enable")
    session.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
    return session


def _per_script(session):
    """The coverage entries merged per script: scriptId -> {startOffset: [name, count]}."""
    merged = {}
    for entry in session.send("Profiler.takePreciseCoverage")["result"]:
        functions = merged.setdefault(entry["scriptId"], {})
        for function in entry["functions"]:
            if not function["ranges"]:
                continue
            own = function["ranges"][0]
            record = functions.setdefault(own["startOffset"], [function["functionName"], 0])
            record[1] = max(record[1], own["count"])
    return merged


def measure(session):
    """(executed, total, where the never-run ones are) for the page's own script.

    The never-run list names a line rather than only a function name, because the
    functions a suite has not reached are mostly anonymous callbacks: reported by
    name alone they collapse into one entry and the list stops being actionable.
    """
    executed = total = 0
    never = []
    for script_id, functions in _per_script(session).items():
        source = session.send("Debugger.getScriptSource", {"scriptId": script_id})["scriptSource"]
        if not any(marker in source for marker in PAGE_MARKERS):
            continue
        for offset, (name, count) in functions.items():
            total += 1
            if count > 0:
                executed += 1
            else:
                line = source.count("\n", 0, offset) + 1
                never.append(f"line {line}: {name or '(anonymous)'}")
    return executed, total, never


def report(session):
    """Print the number and the unrun lines, and return the percentage."""
    executed, total, never = measure(session)
    percent = 100 * executed / total if total else 0.0
    print(f"\nthe page's own script: {executed}/{total} functions ran ({percent:.1f}%)")
    print(f"never ran: {len(never)}")
    for where in sorted(never):
        print(f"  {where}")
    return percent
