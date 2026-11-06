from pathlib import Path

from py_call_linter import Location

PROJECT = (Path(__file__).parent / "fixture_project").resolve()


def find(path: Path, text: str, *, nth: int = 1) -> Location:
    """The location of ``text`` on the ``nth`` line of ``path`` containing it."""
    matches = [
        (number, line)
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if text in line
    ]
    number, line = matches[nth - 1]
    return Location(path=path, line=number, column=line.index(text) + 1)


def name_in(path: Path, line_text: str, name: str) -> Location:
    """The location of ``name`` within the first line of ``path`` with ``line_text``."""
    line = find(path, line_text)
    return line.model_copy(update={"column": line.column + line_text.index(name)})
