"""Command line for the foundation stage."""
import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .documentation import initialize_project
from .validation import REQUIRED_FILES, validate_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="site-transfer")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, description in (("validate", "Validate configuration"), ("plan", "Print a non-executing plan"), ("init", "Generate target documentation")):
        command = commands.add_parser(name, help=description)
        command.add_argument("config", type=Path)
        if name == "init":
            command.add_argument("--output", type=Path, required=True)
    project = commands.add_parser("validate-project", help="Check required target documents")
    project.add_argument("path", type=Path)
    publish = commands.add_parser("publish", help="Publish reviewed kit to a private GitHub repository as draft PR")
    publish.add_argument("kit",type=Path)
    publish.add_argument("--repo",required=True)
    publish.add_argument("--sha256",required=True)
    publish.add_argument("--approve",action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "publish":
            from .github import publish as publish_kit
            print(json.dumps(publish_kit(args.kit,args.repo,args.sha256,args.approve),indent=2))
            return 0
        if args.command == "validate-project":
            errors = validate_project(args.path)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print("Project documentation valid")
            return 0
        config = load_config(args.config)
        if args.command == "validate":
            print("Configuration valid")
        elif args.command == "plan":
            print(json.dumps({
                "source": config["source"],
                "target": config["target"],
                "viewports": config.get("viewports", [
                    {"name": "desktop", "width": 1440, "height": 900},
                    {"name": "mobile", "width": 390, "height": 844},
                ]),
                "required_documents": list(REQUIRED_FILES),
                "implemented": ["validate", "plan", "init", "validate-project"],
                "pending": ["capture", "verify", "publish", "run"],
                "network_access": False,
                "review_before_push": True,
            }, indent=2, ensure_ascii=False))
        else:
            output = initialize_project(config, args.output)
            print(f"Documentation initialized: {output}")
        return 0
    except (ConfigError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
