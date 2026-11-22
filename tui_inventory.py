"""One-shot inventory entry for a paired widget on a provisioned local TUI."""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys

# Only this pre-inventory verdict allows the caller to use stock CLI dispatch.
UNSUPPORTED = 78


def main() -> int:
    if len(sys.argv) != 4 or not sys.flags.isolated or not sys.flags.no_site:
        return 1
    home, root, packages = map(Path, sys.argv[1:])
    if any(not p.is_absolute() for p in (home, root, packages)) or str(home) != os.environ.get("HERMES_HOME"):
        return 1
    own = home / "plugins" / "session-pins"
    if (own / "tui_inventory.py").resolve() != Path(__file__).resolve():
        return 1
    if any(os.environ.get(k, "").strip().lower() in {"1", "true", "yes", "on"}
           for k in ("HERMES_SAFE_MODE", "HERMES_IGNORE_USER_CONFIG")):
        return 1
    if (Path("/etc/hermes").exists() or os.environ.get("HERMES_MANAGED_DIR")
            or packages.name != "site-packages" or packages.parent.name != f"python{sys.version_info.major}.{sys.version_info.minor}"
            or not packages.is_dir() or not (root / "hermes_state.py").is_file()):
        return UNSUPPORTED
    sys.path[:0] = [str(root.resolve()), str(packages.resolve())]
    try:
        from hermes_cli.version_info import get_version_info
        from hermes_cli.config import read_raw_config_readonly
        from hermes_constants import get_hermes_home
        from packaging.specifiers import SpecifierSet
        from packaging.version import InvalidVersion, Version
        from ruamel.yaml import YAML
    except ImportError:
        return UNSUPPORTED
    if Path(get_hermes_home()) != home or (home / "state.db").resolve().parent != home.resolve():
        return 1

    # Qualify only literal entries in the ordinary local profile allow/deny
    # lists. Not a plugin discovery engine: let stock dispatch interpret other
    # config shapes, env expansion and special deployment policies.
    config = read_raw_config_readonly().get("plugins")
    if not isinstance(config, dict):
        return UNSUPPORTED
    enabled, disabled = config.get("enabled", []), config.get("disabled", [])
    if any(not isinstance(items, list) or any(not isinstance(name, str) or
           not re.fullmatch(r"[A-Za-z0-9_./-]+", name) for name in items) for items in (enabled, disabled)):
        return UNSUPPORTED
    if "session-pins" not in enabled or "session-pins" in disabled:
        return 1
    manifest = YAML(typ="safe").load((own / "plugin.yaml").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("name") != "session-pins" or manifest.get("kind") != "standalone":
        return 1
    try:
        # Qualify the manifest we ship, not arbitrary plugin dependency rules.
        if (manifest.get("requires_hermes") != ">=0.22.5" or
                Version(get_version_info().base_version) not in SpecifierSet(manifest["requires_hermes"]) or
                manifest.get("requires_plugins") or manifest.get("depends") or manifest.get("hermes")):
            return UNSUPPORTED
    except InvalidVersion:
        return UNSUPPORTED

    sys.path.append(str(own.resolve()))
    from tui_bridge import inventory_json

    print(inventory_json(home))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        code = 1  # Do not forward native errors, SQL, config or partial rows.
    raise SystemExit(code)
