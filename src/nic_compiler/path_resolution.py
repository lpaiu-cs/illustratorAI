from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path


class ProjectRootNotFoundError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class ProjectPaths:
    project_root: Path
    src_root: Path
    pykrita_root: Path
    examples_root: Path
    assets_root: Path
    logs_root: Path
    plugin_entry: Path | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in asdict(self).items()
        }


def discover_project_root(anchor: Path, explicit_root: Path | None = None) -> Path:
    candidates: list[Path] = []
    env_root = os.environ.get("NIC_DEV_PROJECT_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    if explicit_root is not None:
        candidates.append(explicit_root)

    resolved_anchor = anchor.resolve()
    start_dir = resolved_anchor if resolved_anchor.is_dir() else resolved_anchor.parent
    candidates.extend([start_dir, *start_dir.parents])

    for candidate in candidates:
        candidate = candidate.resolve()
        if _looks_like_project_root(candidate):
            return candidate

    raise ProjectRootNotFoundError(
        f"Could not resolve project root from anchor: {anchor}"
    )


def build_project_paths(anchor: Path, explicit_root: Path | None = None) -> ProjectPaths:
    project_root = discover_project_root(anchor, explicit_root=explicit_root)
    return ProjectPaths(
        project_root=project_root,
        src_root=project_root / "src",
        pykrita_root=project_root / "pykrita",
        examples_root=project_root / "examples",
        assets_root=project_root / "examples" / "assets",
        logs_root=project_root / ".nic_dev_logs",
        plugin_entry=anchor.resolve() if anchor else None,
    )


def default_output_root(project_root: Path, source_path: Path) -> Path:
    return project_root.resolve() / ".nic_dev_build" / source_path.stem


def ensure_output_root(path: Path) -> Path:
    resolved = path.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_output_root(
    project_root: Path,
    source_path: Path,
    explicit_output_root: Path | None = None,
) -> Path:
    return ensure_output_root(
        explicit_output_root.resolve()
        if explicit_output_root is not None
        else default_output_root(project_root, source_path)
    )


def export_output_path(output_root: Path, requested_name: str | None, fallback_name: str) -> Path:
    leaf_name = Path(requested_name).name if requested_name else fallback_name
    return output_root / leaf_name


def report_output_path(output_root: Path, source_stem: str) -> Path:
    return output_root / f"{source_stem}_compile_report.json"


def manifest_output_path(output_root: Path, document_name: str) -> Path:
    return output_root / f"{document_name}_manifest.json"


def resolve_demo_path(project_paths: ProjectPaths, demo_name: str) -> Path:
    return project_paths.examples_root / demo_name


def _looks_like_project_root(candidate: Path) -> bool:
    return (
        (candidate / "pyproject.toml").is_file()
        and (candidate / "src" / "nic_compiler").is_dir()
        and (candidate / "src" / "nic_ir").is_dir()
        and (candidate / "pykrita").is_dir()
        and (candidate / "examples").is_dir()
    )

