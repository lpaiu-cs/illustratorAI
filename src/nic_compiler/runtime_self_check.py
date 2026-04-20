from __future__ import annotations

import importlib
import platform
import sys
from pathlib import Path
from typing import Any

from nic_compiler.path_resolution import ProjectPaths
from nic_compiler.reporting import SelfCheckItem


def collect_environment_info(session: Any | None = None) -> dict[str, Any]:
    krita_version = None
    if session is not None:
        try:
            krita_version = session.runtime_version()
        except Exception:
            krita_version = None
    return {
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "krita_version": krita_version,
    }


def run_runtime_self_check(
    project_paths: ProjectPaths,
    *,
    source_path: Path | None,
    output_root: Path,
    session: Any | None = None,
    require_krita: bool,
) -> list[SelfCheckItem]:
    checks: list[SelfCheckItem] = []

    checks.append(_path_exists_check("project_root", project_paths.project_root, critical=True))
    checks.append(_path_exists_check("src_root", project_paths.src_root, critical=True))
    checks.append(_path_exists_check("examples_root", project_paths.examples_root, critical=False))
    checks.append(_path_exists_check("assets_root", project_paths.assets_root, critical=False))
    if source_path is not None:
        checks.append(_path_exists_check("source_ir", source_path, critical=True))

    checks.extend(_module_import_checks())
    checks.append(_output_root_check(output_root))
    checks.extend(_runtime_checks(session=session, require_krita=require_krita))

    demo_names = ("demo_anime_bust.json", "demo_vector_accessories.json")
    for demo_name in demo_names:
        checks.append(
            _path_exists_check(
                f"bundled_demo:{demo_name}",
                project_paths.examples_root / demo_name,
                critical=False,
            )
        )
    return checks


def has_critical_failures(checks: list[SelfCheckItem]) -> bool:
    return any(check.critical and check.status == "fail" for check in checks)


def _module_import_checks() -> list[SelfCheckItem]:
    checks: list[SelfCheckItem] = []
    required_modules = [
        "nic_ir.validator",
        "nic_compiler.compiler",
        "nic_compiler.path_resolution",
        "nic_compiler.reporting",
    ]
    for module_name in required_modules:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            checks.append(
                SelfCheckItem(
                    name=f"import:{module_name}",
                    status="fail",
                    message=str(exc),
                    critical=True,
                )
            )
        else:
            checks.append(
                SelfCheckItem(
                    name=f"import:{module_name}",
                    status="pass",
                    message="import ok",
                    critical=True,
                )
            )
    return checks


def _output_root_check(output_root: Path) -> SelfCheckItem:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        probe = output_root / ".nic_write_probe"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except Exception as exc:
        return SelfCheckItem(
            name="output_root_writable",
            status="fail",
            message=str(exc),
            critical=True,
            details={"output_root": str(output_root)},
        )
    return SelfCheckItem(
        name="output_root_writable",
        status="pass",
        message="output root is writable",
        critical=True,
        details={"output_root": str(output_root)},
    )


def _runtime_checks(session: Any | None, require_krita: bool) -> list[SelfCheckItem]:
    if session is None:
        return [
            SelfCheckItem(
                name="krita_api_import",
                status="warn" if not require_krita else "fail",
                message="no Krita session provided",
                critical=require_krita,
            ),
            SelfCheckItem(
                name="brush_api",
                status="warn",
                message="runtime probe skipped",
                critical=False,
            ),
            SelfCheckItem(
                name="transform_payload_support",
                status="warn",
                message="runtime probe skipped",
                critical=False,
            ),
        ]

    import_ok = session.runtime_import_available()
    checks = [
        SelfCheckItem(
            name="krita_api_import",
            status="pass" if import_ok else ("warn" if not require_krita else "fail"),
            message="krita module import available" if import_ok else "krita module unavailable",
            critical=require_krita,
        )
    ]
    if not import_ok:
        checks.extend(
            [
                SelfCheckItem(
                    name="brush_api",
                    status="warn",
                    message="runtime unavailable",
                    critical=False,
                ),
                SelfCheckItem(
                    name="transform_payload_support",
                    status="warn",
                    message="runtime unavailable",
                    critical=False,
                ),
            ]
        )
        return checks

    try:
        capabilities = session.probe_runtime_capabilities()
    except Exception as exc:
        checks.extend(
            [
                SelfCheckItem(
                    name="brush_api",
                    status="warn",
                    message=f"capability probe failed: {exc}",
                    critical=False,
                ),
                SelfCheckItem(
                    name="transform_payload_support",
                    status="warn",
                    message="capability probe unavailable",
                    critical=False,
                ),
            ]
        )
        return checks

    brush_available = capabilities.has_brush_line or capabilities.has_brush_path
    checks.append(
        SelfCheckItem(
            name="brush_api",
            status="pass" if brush_available else "warn",
            message=(
                "brush API surface available"
                if brush_available
                else "brush API surface missing; fallback path expected"
            ),
            critical=False,
            details=capabilities.to_dict(),
        )
    )
    checks.append(
        SelfCheckItem(
            name="transform_payload_support",
            status="warn",
            message="transform mask payload application is intentionally not implemented in v0",
            critical=False,
            details={"supported": False},
        )
    )
    return checks


def _path_exists_check(name: str, path: Path, critical: bool) -> SelfCheckItem:
    exists = path.exists()
    return SelfCheckItem(
        name=name,
        status="pass" if exists else "fail",
        message="exists" if exists else "missing",
        critical=critical,
        details={"path": str(path)},
    )

