"""Reading + validating Allsky's settings.json against options.json schema.

Source of truth for setting *values* stays Allsky's own settings.json. We never
maintain a parallel copy. Validation is performed against options.json which
upstream Allsky generates per camera type at install time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .paths import paths


@dataclass
class SettingDef:
    name: str
    type: str
    label: str
    description: str = ""
    default: Any = None
    minimum: Any = None
    maximum: Any = None
    tab: str = ""
    section: str = ""
    depends_on: str | None = None
    advanced: bool = False
    usage: str | None = None
    # `options` may be a list of {value,label} dicts OR a list of camera-driver
    # placeholder strings like ["bin_values"] which the upstream PHP layer
    # resolves at install time. We pass them through unchanged.
    options: list | None = None
    action: str | None = None
    raw: dict | None = None


def _coerce_number(value: Any) -> Any:
    """options.json sometimes uses sentinel strings like '_min' or 'day_default'.
    Those are camera-driver-supplied placeholders. Return None for now."""
    if isinstance(value, str) and (value.startswith("_") or value.endswith("_default")):
        return None
    return value


def load_schema() -> list[SettingDef]:
    """Parse options.json into an ordered list of SettingDef.

    The upstream file is a flat array of entries; some entries are layout
    markers (header-tab, header, header-column) which we use to assign each
    real setting to a tab + section.
    """
    options_path = paths().options_file
    if not options_path.exists():
        return []

    with options_path.open() as f:
        raw = json.load(f)

    defs: list[SettingDef] = []
    current_tab = ""
    current_section = ""

    for entry in raw:
        etype = entry.get("type", "")
        label = entry.get("label", "")

        if etype == "header-tab":
            current_tab = label
            current_section = ""
            continue
        if etype == "header":
            current_section = label
            continue
        if etype in ("header-column",):
            continue
        # Real setting.
        name = entry.get("name", "")
        if not name or name.startswith("XX_") or "===" in name:
            continue

        defs.append(
            SettingDef(
                name=name,
                type=etype or "string",
                label=label or name,
                description=entry.get("description", ""),
                default=_coerce_number(entry.get("default")),
                minimum=_coerce_number(entry.get("minimum")),
                maximum=_coerce_number(entry.get("maximum")),
                tab=current_tab,
                section=current_section,
                depends_on=entry.get("booldependson"),
                advanced=bool(entry.get("advanced", False)),
                usage=entry.get("usage"),
                options=entry.get("options"),
                action=entry.get("action"),
                raw=entry,
            )
        )

    return defs


def load_values() -> dict[str, Any]:
    """Read the active settings.json. Returns {} if Allsky isn't installed yet.

    Upstream Allsky stores booleans as "true"/"false" strings and numbers as
    strings. We coerce them to proper Python types based on the schema so the
    frontend gets clean data.
    """
    settings_path = paths().settings_file
    if not settings_path.exists():
        return {}
    with settings_path.open() as f:
        raw = json.load(f)

    # Coerce values based on schema types.
    schema_by_name = {d.name: d for d in load_schema()}
    for key, value in list(raw.items()):
        d = schema_by_name.get(key)
        if d is None:
            continue
        if d.type == "boolean" and isinstance(value, str):
            raw[key] = value.lower() in ("true", "1", "yes", "on")
        elif d.type in ("integer",) and isinstance(value, str):
            try:
                raw[key] = int(value)
            except ValueError:
                pass
        elif d.type in ("float", "percent") and isinstance(value, str):
            try:
                raw[key] = float(value)
            except ValueError:
                pass
    return raw


def save_values(values: dict[str, Any]) -> None:
    """Write settings.json to both the web config copy and the allsky home copy.

    The web config copy (/opt/allsky-web/config/) is what the web UI reads.
    The allsky home copy (~/allsky/config/) is what the camera daemon reads.
    Both must stay in sync.
    """
    import logging
    import os
    log = logging.getLogger(__name__)
    p = paths()
    for target in (p.settings_file, p.settings_file_allsky_home):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            with tmp.open("w") as f:
                json.dump(values, f, indent=4)
            os.replace(str(tmp), str(target))
            log.info("settings saved to %s", target)
        except OSError as e:
            log.warning("failed to save settings to %s: %s", target, e)


def grouped_schema() -> dict[str, dict[str, list[dict]]]:
    """Group schema by tab → section → entries, in upstream display order.

    Returned shape is JSON-serialisable so we can hand it straight to React.
    """
    out: dict[str, dict[str, list[dict]]] = {}
    for d in load_schema():
        tab = d.tab or "Other"
        section = d.section or ""
        out.setdefault(tab, {}).setdefault(section, []).append(
            {
                "name": d.name,
                "type": d.type,
                "label": d.label,
                "description": d.description,
                "default": d.default,
                "minimum": d.minimum,
                "maximum": d.maximum,
                "depends_on": d.depends_on,
                "advanced": d.advanced,
                "usage": d.usage,
                "options": d.options,
                "action": d.action,
            }
        )
    return out


def validate_patch(patch: dict[str, Any]) -> list[str]:
    """Return a list of human-readable validation errors for a proposed update.

    Empty list = OK.
    """
    errors: list[str] = []
    schema_by_name = {d.name: d for d in load_schema()}

    for key, value in list(patch.items()):
        d = schema_by_name.get(key)
        if d is None:
            # Don't reject unknown settings — upstream may add new ones.
            continue

        # Coerce string booleans to real booleans before validation.
        if d.type == "boolean":
            if isinstance(value, str):
                patch[key] = value.lower() in ("true", "1", "yes", "on")
            elif not isinstance(value, bool):
                errors.append(f"{key}: expected boolean, got {type(value).__name__}")
            continue

        if d.type in ("integer",):
            if isinstance(value, bool):
                errors.append(f"{key}: expected integer, got bool")
                continue
            if isinstance(value, str):
                try:
                    patch[key] = int(value)
                    value = patch[key]
                except ValueError:
                    try:
                        # Handle "0.0" → 0 for integer fields.
                        patch[key] = int(float(value))
                        value = patch[key]
                    except ValueError:
                        errors.append(f"{key}: expected integer, got {value!r}")
                        continue
            elif not isinstance(value, int):
                errors.append(f"{key}: expected integer")
                continue
        if d.type in ("float", "percent"):
            if isinstance(value, bool):
                errors.append(f"{key}: expected number, got bool")
                continue
            if isinstance(value, str):
                try:
                    patch[key] = float(value)
                    value = patch[key]
                except ValueError:
                    errors.append(f"{key}: expected number, got {value!r}")
                    continue
            elif not isinstance(value, (int, float)):
                errors.append(f"{key}: expected number")
                continue

        if d.minimum is not None and isinstance(value, (int, float)):
            try:
                if value < float(d.minimum):
                    errors.append(f"{key}: value {value} below minimum {d.minimum}")
            except (TypeError, ValueError):
                pass
        if d.maximum is not None and isinstance(value, (int, float)):
            try:
                if value > float(d.maximum):
                    errors.append(f"{key}: value {value} above maximum {d.maximum}")
            except (TypeError, ValueError):
                pass

    return errors
