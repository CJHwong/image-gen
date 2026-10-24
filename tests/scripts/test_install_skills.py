import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install_skills.py"
spec = importlib.util.spec_from_file_location("install_skills", SCRIPT)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def a_skill(root: Path, name: str) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"# {name}\n")
    return skill


def test_a_skills_folder_linked_from_another_agent_is_installed_once(tmp_path):
    (tmp_path / ".agents" / "skills").mkdir(parents=True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills").symlink_to(tmp_path / ".agents" / "skills")

    assert installer.skill_folders(tmp_path) == [tmp_path / ".agents" / "skills"]


def test_an_agent_folder_without_skills_gets_one_and_a_missing_agent_gets_none(tmp_path):
    (tmp_path / ".codex").mkdir()

    assert installer.skill_folders(tmp_path) == [tmp_path / ".codex" / "skills"]


def test_an_installed_skill_is_replaced_with_a_warning(tmp_path):
    skill = a_skill(tmp_path / "source", "studio-image")
    old = a_skill(tmp_path / "skills", "studio-image")
    (old / "stale.md").write_text("old")

    line = installer.install(skill, tmp_path / "skills")

    assert line.startswith("warning: replaced the existing")
    assert not (old / "stale.md").exists()
    assert (old / "SKILL.md").read_text() == "# studio-image\n"


def test_a_linked_skill_loses_the_link_and_keeps_its_target(tmp_path):
    skill = a_skill(tmp_path / "source", "studio-image")
    working_copy = a_skill(tmp_path / "mine", "studio-image")
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "studio-image").symlink_to(working_copy)

    line = installer.install(skill, tmp_path / "skills")

    assert line.startswith("warning: replaced the link")
    assert (working_copy / "SKILL.md").exists()
    assert not (tmp_path / "skills" / "studio-image").is_symlink()


def test_a_clone_installs_only_its_tracked_skills(tmp_path):
    repo = tmp_path / "repo"
    a_skill(repo / "skills", "tracked")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "skills"], check=True)
    a_skill(repo / "skills", "untracked")
    (tmp_path / "staging").mkdir()

    source = installer.local_skills(repo, tmp_path / "staging")

    assert [s.name for s in installer.skills_in(source)] == ["tracked"]


def test_a_home_without_any_agent_folder_installs_nothing(tmp_path, capsys):
    repo = tmp_path / "repo"
    a_skill(repo / "skills", "studio-image")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "skills"], check=True)
    (tmp_path / "staging").mkdir()
    (tmp_path / "home").mkdir()

    assert installer.run(repo, tmp_path / "staging", tmp_path / "home") == 1
    assert "none of ~/.agents, ~/.codex or ~/.claude exists" in capsys.readouterr().err
