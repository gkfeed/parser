"""List the first statement reaching triple nesting in each branch."""

import argparse
import ast
from collections.abc import Iterator, Sequence
from pathlib import Path

BLOCKS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def find_nesting(
    node: ast.AST,
    depth: int = 0,
    scope: str = "<module>",
    reported: bool = False,
) -> Iterator[tuple[int, str, str]]:
    if isinstance(node, SCOPES):
        depth, reported = 0, False
        scope = getattr(node, "name", "<lambda>")
    depth += int(isinstance(node, BLOCKS))
    if isinstance(node, ast.stmt) and depth >= 3 and not reported:
        yield node.lineno, scope, type(node).__name__
        reported = True

    for child in ast.iter_child_nodes(node):
        is_elif = (
            isinstance(node, ast.If)
            and isinstance(child, ast.If)
            and child in node.orelse
            and child.col_offset == node.col_offset
        )
        yield from find_nesting(child, depth - int(is_elif), scope, reported)


def python_files(paths: Sequence[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_file():
            files.add(path)
            continue
        files.update(path.rglob("*.py"))
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    files = python_files(args.paths)
    count = 0
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for line, scope, kind in find_nesting(tree):
            print(f"{path}:{line}: {scope}: nesting >= 3 ({kind})")
            count += 1
    print(f"Scanned {len(files)} files; {count} nesting candidates.")
    print("Review candidates manually; this scan does not inspect expressions.")


if __name__ == "__main__":
    main()
