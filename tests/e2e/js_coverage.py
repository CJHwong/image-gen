"""How much of the page's own code ran during a browser session.

Chrome counts a function as run when its own range was entered. Counting bytes
instead would flatter any suite: most of the page's characters are the one-time
startup that every load runs, so a byte figure sits near 90 percent however
little of the page a suite presses.

What counts as the page's own code is where a script came from, not what it
says. The code lives in two places, and each is recognised by the url the
coverage entry carries: the inline scripts of the document, which are reported
under the document's own url, and the modules the studio serves under `/page/`
on its own origin. A marker string would leave with the code it marked, and this
report has to keep reading while the refactor moves the code out of the inline
script into those modules.

Both tests are also what keeps every other script out of the count. The modules
a library serves from a CDN are another origin, and the browser automation
injects scripts of its own into the page, which are reported with an empty url:
measured, so neither is the document's url and neither is under `/page/`.

Two things about how V8 reports coverage decide how this reads it.

V8 may report one script across several entries, so the entries are merged per
scriptId first. Without that merge the same script is counted twice and the
totals drift between runs of an unchanged page, which makes the number unusable
as a target. And a function is keyed by where its own range starts, not by its
name: most handlers in the page are anonymous, and keying on the name would
collapse all of them into one entry.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The two places the page's code lives, and what to print when one of them holds
# nothing. The inline script goes last in this refactor, so its line has to be
# able to say it is gone rather than print a coverage of zero, which a reader
# would take for a total loss.
SOURCES = (
    ("inline script", "none left: the page's code is all in modules"),
    ("modules", "none loaded"),
)
INLINE, MODULES = [label for label, _ in SOURCES]


def start(page):
    """Begin precise coverage. Call it before the navigation, or startup is lost."""
    session = page.context.new_cdp_session(page)
    session.send("Debugger.enable")
    session.send("Profiler.enable")
    session.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
    return session


def _per_script(session):
    """The coverage entries merged per script: scriptId -> (url, {startOffset: [name, count]})."""
    merged = {}
    for entry in session.send("Profiler.takePreciseCoverage")["result"]:
        functions = merged.setdefault(entry["scriptId"], (entry["url"], {}))[1]
        for function in entry["functions"]:
            if not function["ranges"]:
                continue
            own = function["ranges"][0]
            record = functions.setdefault(own["startOffset"], [function["functionName"], 0])
            record[1] = max(record[1], own["count"])
    return merged


def _asked(session, expression):
    """One value out of the page the session watches."""
    return session.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})["result"]["value"]


def _source_of(url, document, origin):
    """Which of the two the script is, or None for a script that is not the page's.

    The document's own url is what V8 reports for the document's inline scripts
    and for nothing else, and the studio serves its modules under `/page/` on
    the origin it serves the document from.
    """
    if url == document:
        return INLINE
    return MODULES if url.startswith(origin + "/page/") else None


def measure(session):
    """(executed, total, where the never-run ones are, per source) for the page's own code.

    The never-run list names the script and the line, because the functions a
    suite has not reached are mostly anonymous callbacks: reported by name alone
    they collapse into one entry, and with two scripts in the count a line alone
    does not say which one. The line is where the function starts in its own
    script, since an inline script is reported without its place in the page.
    """
    executed = total = 0
    never = []
    reached = {label: [0, 0] for label, _ in SOURCES}
    origin = _asked(session, "location.origin")
    document = _asked(session, "location.href")
    for script_id, (url, functions) in _per_script(session).items():
        source_of = _source_of(url, document, origin)
        if source_of is None:
            continue
        source = session.send("Debugger.getScriptSource", {"scriptId": script_id})["scriptSource"]
        where = "inline" if source_of == INLINE else url.removeprefix(origin + "/page/")
        for offset, (name, count) in functions.items():
            total += 1
            reached[source_of][1] += 1
            if count > 0:
                executed += 1
                reached[source_of][0] += 1
            else:
                line = source.count("\n", 0, offset) + 1
                never.append(f"{where} line {line}: {name or '(anonymous)'}")
    return executed, total, never, {label: tuple(counts) for label, counts in reached.items()}


def report(session):
    """Print the number, where the page's code lives, and the unrun lines, and return the percentage."""
    executed, total, never, reached = measure(session)
    print()
    if not total:
        print("no code of the page's own was on this page: nothing inline, and nothing under /page/")
        return 0.0
    percent = 100 * executed / total
    print(f"the page's own code: {executed}/{total} functions ran ({percent:.1f}%)")
    for label, empty in SOURCES:
        ran, count = reached[label]
        print(f"  {label}: " + (f"{ran}/{count} ({100 * ran / count:.1f}%)" if count else empty))
    print(f"never ran: {len(never)}")
    for where in sorted(never):
        print(f"  {where}")
    return percent
