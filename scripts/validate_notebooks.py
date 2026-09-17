"""Validate ExoCore notebook structure and local Markdown links."""

import json
import os
import re
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = REPOSITORY_ROOT / "ExoCore"
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
EXTERNAL_SCHEMES = ("data:", "mailto:")


def has_exact_case(path):
    """Return whether every existing path component has the requested case."""
    normalized = Path(os.path.abspath(path))
    current = Path(normalized.anchor)
    for part in normalized.parts[1:]:
        if not current.is_dir() or part not in {entry.name for entry in current.iterdir()}:
            return False
        current /= part
    return True


def local_targets(source):
    """Yield nonempty local targets from Markdown source."""
    for raw_target in MARKDOWN_LINK.findall(source):
        target = raw_target.strip().split("#", 1)[0].strip("<>")
        if target and "://" not in target and not target.startswith(EXTERNAL_SCHEMES):
            yield unquote(target)


def validate_notebook(notebook_path):
    """Return integrity errors for one notebook."""
    print(f"Reading from {notebook_path}...")
    try:
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{notebook_path}: invalid notebook JSON: {error}"]

    errors = []
    cells = notebook.get("cells", [])
    if not cells:
        errors.append(f"{notebook_path}: notebook has no cells")
    elif not any("".join(cell.get("source", [])).strip() for cell in cells):
        errors.append(f"{notebook_path}: all notebook cells are empty")

    for cell_index, cell in enumerate(cells):
        if cell.get("cell_type") != "markdown":
            continue
        attachments = cell.get("attachments", {})
        for target in local_targets("".join(cell.get("source", []))):
            if target.startswith("attachment:"):
                attachment = target.removeprefix("attachment:")
                if attachment not in attachments:
                    errors.append(
                        f"{notebook_path}: cell {cell_index}: missing attachment {attachment}"
                    )
                continue

            resolved = notebook_path.parent / target.replace("\\", "/")
            if not resolved.exists() or not has_exact_case(resolved):
                errors.append(
                    f"{notebook_path}: cell {cell_index}: missing local target {target}"
                )
    return errors


def main():
    """Validate all curriculum notebooks."""
    notebook_paths = sorted(NOTEBOOK_ROOT.glob("**/*.ipynb"))
    if not notebook_paths:
        raise SystemExit(f"No notebooks found under {NOTEBOOK_ROOT}.")
    errors = [
        error
        for notebook_path in notebook_paths
        for error in validate_notebook(notebook_path)
    ]
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Validated {len(notebook_paths)} notebooks.")


if __name__ == "__main__":
    main()