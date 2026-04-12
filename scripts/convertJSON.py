#!/usr/bin/env python3
"""Drop-in Python replacement for convertJSON.php.

Reads settings.json and options.json and outputs settings as shell variable
assignments or key=value pairs. This eliminates the PHP dependency.

Usage (matches the PHP script's interface):
  convertJSON.py --prefix S_ --shell --variables "var1 var2 ..."
  convertJSON.py --capture-only --delimiter "="
  convertJSON.py --convert
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Convert Allsky JSON settings to shell vars")
    parser.add_argument("--settings-file", default=None)
    parser.add_argument("--options-file", default=None)
    parser.add_argument("--delimiter", default="=")
    parser.add_argument("--type", dest="type_filter", default="")
    parser.add_argument("--settings-only", action="store_true")
    parser.add_argument("--capture-only", action="store_true")
    parser.add_argument("--options-only", action="store_true")
    parser.add_argument("--carryforward", action="store_true")
    parser.add_argument("--null", action="store_true", dest="output_null")
    parser.add_argument("--convert", action="store_true")
    parser.add_argument("--order", action="store_true")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--variables", default=None)
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    allsky_home = os.environ.get("ALLSKY_HOME", str(Path.home() / "allsky"))

    # Find settings file.
    if args.settings_file:
        settings_path = Path(args.settings_file)
    else:
        # Check web config copy first, then allsky home.
        web_config = os.environ.get("ALLSKY_WEB_CONFIG", "")
        candidates = []
        if web_config:
            candidates.append(Path(web_config) / "settings.json")
        candidates.append(Path(allsky_home) / "config" / "settings.json")
        settings_path = next((c for c in candidates if c.exists()), candidates[-1])

    # Find options file.
    if args.options_file:
        options_path = Path(args.options_file)
    else:
        web_config = os.environ.get("ALLSKY_WEB_CONFIG", "")
        candidates = []
        if web_config:
            candidates.append(Path(web_config) / "options.json")
        candidates.append(Path(allsky_home) / "config" / "options.json")
        options_path = next((c for c in candidates if c.exists()), candidates[-1])

    # Load settings.
    settings: dict = {}
    if settings_path.exists():
        try:
            with settings_path.open() as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"ERROR: Cannot read settings file '{settings_path}': {e}", file=sys.stderr)
            sys.exit(1)

    # Load options (schema).
    options: list[dict] = []
    options_by_name: dict[str, dict] = {}
    if options_path.exists():
        try:
            with options_path.open() as f:
                options = json.load(f)
            for entry in options:
                name = entry.get("name", "")
                if name:
                    options_by_name[name] = entry
        except (json.JSONDecodeError, OSError) as e:
            print(f"ERROR: Cannot read options file '{options_path}': {e}", file=sys.stderr)
            sys.exit(1)

    # Determine which variables to output.
    requested_vars = None
    if args.variables:
        requested_vars = set(args.variables.split())

    # Build output list.
    output: list[tuple[str, str, str]] = []  # (name, value_str, type)

    # Determine iteration order.
    if args.order:
        # Order by options file order, then append any extras.
        seen = set()
        for entry in options:
            name = entry.get("name", "")
            if not name:
                continue
            seen.add(name)
            if name in settings:
                value = settings[name]
                otype = entry.get("type", "string")
                output.append((name, value, otype))
        # Add settings not in options.
        for name, value in settings.items():
            if name not in seen:
                output.append((name, value, "string"))
    else:
        for name, value in settings.items():
            otype = options_by_name.get(name, {}).get("type", "string")
            output.append((name, value, otype))

    # Apply filters.
    filtered = []
    for name, value, otype in output:
        if requested_vars and name not in requested_vars:
            # Also check with prefix stripped.
            if args.prefix and f"{args.prefix}{name}" not in requested_vars:
                continue

        if args.capture_only:
            opt = options_by_name.get(name, {})
            if opt.get("usage") != "capture":
                continue

        if args.carryforward:
            opt = options_by_name.get(name, {})
            if not opt.get("carryforward"):
                continue

        if args.options_only:
            if name not in options_by_name:
                continue

        if args.settings_only:
            if name not in settings:
                continue

        if args.type_filter:
            opt = options_by_name.get(name, {})
            if opt.get("type") != args.type_filter:
                continue

        filtered.append((name, value, otype))

    # Convert mode — output full JSON.
    if args.convert:
        result = {}
        for name, value, otype in filtered:
            name_lower = name.lower()
            if otype == "boolean":
                if isinstance(value, str):
                    value = value.lower() in ("true", "1", "yes")
                result[name_lower] = bool(value)
            elif otype in ("integer",):
                try:
                    result[name_lower] = int(value)
                except (ValueError, TypeError):
                    result[name_lower] = value
            elif otype in ("float", "percent"):
                try:
                    result[name_lower] = float(value)
                except (ValueError, TypeError):
                    result[name_lower] = value
            else:
                result[name_lower] = str(value) if value is not None else ""
        print(json.dumps(result, indent=4))
        return

    # Output.
    for name, value, otype in filtered:
        full_name = f"{args.prefix}{name}"

        # Format value.
        if value is None:
            val_str = "null" if args.output_null else ""
        elif isinstance(value, bool):
            val_str = "true" if value else "false"
        else:
            val_str = str(value)

        if args.shell:
            # Shell eval format: NAME='value'
            val_quoted = quote_for_shell(val_str, otype)
            print(f"{full_name}={val_quoted}")
        elif args.carryforward:
            print(f"{full_name}{args.delimiter}{otype}")
        else:
            print(f"{full_name}{args.delimiter}{val_str}")


def quote_for_shell(value: str, otype: str) -> str:
    """Quote a value for shell eval, matching PHP convertJSON behavior."""
    if otype in ("boolean", "float", "integer", "percent"):
        return value
    # Single-quote, escaping internal single quotes.
    return "'" + value.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    main()
