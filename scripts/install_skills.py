# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Install Open Imagine's agent skills into each agent's skill folder.

    uv run https://raw.githubusercontent.com/CJHwong/open-imagine/main/scripts/install_skills.py

Run from a clone, it installs that clone's tracked skills instead of main's. It installs into
~/.agents/skills, ~/.codex/skills and ~/.claude/skills, for each of those agent folders that
exists. A skill already installed there is replaced, with a warning.
"""

import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ARCHIVE = "https://codeload.github.com/CJHwong/open-imagine/tar.gz/refs/heads/main"
AGENT_FOLDERS = (".agents", ".codex", ".claude")


def skill_folders(home: Path) -> list[Path]:
    """One skills/ folder per real location: ~/.claude/skills is often a link to ~/.agents/skills."""
    seen, folders = set(), []
    for name in AGENT_FOLDERS:
        agent = home / name
        if not agent.is_dir():
            continue
        folder = agent / "skills"
        real = folder.resolve()
        if real not in seen:
            seen.add(real)
            folders.append(folder)
    return folders


def local_skills(repo: Path, staging: Path) -> Path | None:
    """The clone's tracked skills/, or None when not run from a clone that git can read."""
    if not (repo / ".git").exists() or not (repo / "skills").is_dir():
        return None
    try:
        listed = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "skills"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"note: cannot list the clone's tracked files ({error}); using GitHub main", file=sys.stderr)
        return None
    for relative in filter(None, listed.stdout.split("\0")):
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / relative, target)
    return staging / "skills"


def downloaded_skills(staging: Path) -> Path:
    """main's skills/ from GitHub, extracted with the safe 'data' filter."""
    with urllib.request.urlopen(ARCHIVE, timeout=60) as response:
        data = io.BytesIO(response.read())
    with tarfile.open(fileobj=data, mode="r:gz") as archive:
        members = [m for m in archive.getmembers() if m.name.split("/")[1:2] == ["skills"]]
        archive.extractall(staging, members=members, filter="data")
    return next(staging.iterdir()) / "skills"


def skills_in(source: Path) -> list[Path]:
    return sorted(path.parent for path in source.glob("*/SKILL.md"))


def install(skill: Path, folder: Path) -> str:
    """Copy one skill into one folder; return the line to report."""
    target = folder / skill.name
    note = ""
    if target.is_symlink():
        # A link usually points at someone's own working copy; remove the link, never its target.
        note = f"warning: replaced the link {target} -> {target.readlink()}"
        target.unlink()
    elif target.exists():
        note = f"warning: replaced the existing {target}"
        shutil.rmtree(target)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill, target)
    return note or f"installed {target}"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="open-imagine-skills-") as staging:
        return run(Path(__file__).resolve().parent.parent, Path(staging), Path.home())


def run(repo: Path, staging: Path, home: Path) -> int:
    source = local_skills(repo, staging)
    origin = f"the clone at {repo}" if source else "GitHub main"
    if source is None:
        try:
            source = downloaded_skills(staging)
        except (OSError, tarfile.TarError) as error:
            print(f"error: could not download {ARCHIVE}: {error}", file=sys.stderr)
            return 1
    skills = skills_in(source)
    folders = skill_folders(home)
    if not skills:
        print(f"error: no skills found in {origin}", file=sys.stderr)
        return 1
    if not folders:
        print("error: none of ~/.agents, ~/.codex or ~/.claude exists; nothing to install into", file=sys.stderr)
        return 1
    print(f"Installing {', '.join(s.name for s in skills)} from {origin}")
    for folder in folders:
        for skill in skills:
            print(install(skill, folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
