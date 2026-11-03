"""Self-check for guard.ps1: every rule blocks, every override and neighbour passes.

    python .claude/hooks/test_guard.py

Copies the guard into a throwaway git repo (on main) so the checks never touch
this checkout. Needs powershell (Windows) or pwsh. Not in CI: pytest.ini only
collects services/.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The human's own overrides must not leak into the expectations.
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("PNP_ALLOW_")}
SHELL = shutil.which("powershell") or shutil.which("pwsh")


def run(repo: Path, tool: str, tool_input: dict, **env: str) -> int:
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(repo)})
    return subprocess.run(
        [SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(repo / ".claude/hooks/guard.ps1")],
        input=payload, capture_output=True, text=True, env={**CLEAN_ENV, **env},
    ).returncode


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / ".claude/hooks").mkdir(parents=True)
        shutil.copy(HERE / "guard.ps1", repo / ".claude/hooks/guard.ps1")
        prompts = repo / "services/kb/src/pnp_okf/prompts.py"
        prompts.parent.mkdir(parents=True)
        prompts.write_text('EXTRACT_PROMPT_VERSION = "6"\nSTATE_PROMPT_VERSION = "1"\n')
        git = ["git", "-C", str(repo)]
        subprocess.run([*git, "init", "-q", "-b", "main"], check=True)

        edit = lambda path, new="x": {"file_path": str(repo / path), "old_string": "y", "new_string": new}  # noqa: E731
        write = lambda path: {"file_path": str(repo / path), "content": "{}"}  # noqa: E731
        bash = lambda cmd: {"command": cmd}  # noqa: E731
        cases = [
            # (expected exit, tool, input, env)
            (2, "Bash", bash("uv run pnp run --limit 1"), {}),
            (2, "Bash", bash('bash -c "pnp extract"'), {}),
            (2, "Bash", bash("pnp run --estimate && pnp run"), {}),
            (0, "Bash", bash("pnp state --estimate"), {}),
            (0, "Bash", bash('git commit -m "docs: explain pnp run"'), {"PNP_ALLOW_MAIN_COMMIT": "1"}),
            (0, "Bash", bash("gh pr create --body-file - <<'EOF'\nruns pnp run once\nEOF"), {}),
            (2, "Edit", edit(".claude/hooks/guard.ps1"), {}),
            (2, "Write", write(".claude/settings.json"), {}),
            (0, "Write", write(".claude/settings.json"), {"PNP_ALLOW_GUARD_EDIT": "1"}),
            (0, "Edit", edit(".claude/agents/verifier.md"), {}),
            (2, "Edit", edit("graph/src/x.py"), {}),
            (2, "Write", {"file_path": str(repo / "graph/x.md"), "content": ""}, {"PNP_ALLOW_PAID": "1"}),
            (0, "Edit", edit("services/kb/x.py"), {}),
            (0, "Edit", {"file_path": "services/kb/x.py", "old_string": "a", "new_string": "b"}, {}),
            (2, "Edit", edit("knowledge/bundle/npcs/x.md"), {}),
            (0, "Edit", edit("knowledge/bundle/npcs/x.md"), {"PNP_ALLOW_BUNDLE_EDIT": "1"}),
            (0, "Edit", edit("knowledge/entity_rules.yaml"), {}),
            (0, "Edit", edit(r"C:\elsewhere\graph\x.py"), {}),
            (2, "Edit", edit(prompts, 'EXTRACT_PROMPT_VERSION = "7"'), {}),
            (2, "Write", {"file_path": str(prompts),
                          "content": 'EXTRACT_PROMPT_VERSION = "6"\nSTATE_PROMPT_VERSION = "2"\n'}, {}),
            (0, "Edit", edit(prompts, 'EXTRACT_PROMPT_VERSION = "6"'), {}),
            (0, "Edit", edit(prompts, 'EXTRACT_PROMPT_VERSION = "7"'), {"PNP_ALLOW_PAID": "1"}),
            (2, "Bash", bash("pnp run"), {}),
            (2, "Bash", bash("cd services/kb && .venv/Scripts/pnp.exe extract --limit 1"), {}),
            (2, "PowerShell", bash("& .venv\\Scripts\\python.exe -m pnp_okf.cli dedup"), {}),
            (2, "Bash", bash("PNP_PROFILE=flagship pnp state"), {}),
            (0, "Bash", bash("pnp run --estimate"), {}),
            (0, "Bash", bash("pnp run"), {"PNP_ALLOW_PAID": "1"}),
            (0, "Bash", bash("pnp check"), {}),
            # Known false positive, accepted: wrappers must not hide a run. Use the Grep tool.
            (2, "Bash", bash("grep -n 'pnp run' docs/x.md"), {}),
            (2, "Bash", bash('git commit -m "x"'), {}),
            (2, "Bash", bash(f'git -C "{repo}" commit -m "x"'), {}),
            (0, "Bash", bash('git commit -m "x"'), {"PNP_ALLOW_MAIN_COMMIT": "1"}),
            (0, "Bash", bash("git status"), {}),
            (0, "Read", {"file_path": str(repo / "graph/x.py")}, {}),
            (0, "Bash", bash(""), {}),
        ]
        failures = [
            f"expected {want}, got {got}: {tool} {inp} {env}"
            for want, tool, inp, env in cases
            if (got := run(repo, tool, inp, **env)) != want
        ]
        subprocess.run([*git, "switch", "-q", "-c", "feat/x"], check=True)
        if run(repo, "Bash", bash('git commit -m "x"')) != 0:
            failures.append("commit on a branch was blocked")
        assert not failures, "\n".join(failures)
        print(f"guard.ps1: {len(cases) + 1} checks passed")


if __name__ == "__main__":
    main()
