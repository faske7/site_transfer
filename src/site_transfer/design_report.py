"""Versioned report writer contract; legacy fields stay readable."""
from importlib.resources import files
import json

from jsonschema import Draft202012Validator


def build_report(url, viewport, screenshot, snapshot, summary, hover, probes):
    report={"schema_version":2,"url":url,"viewport_name":viewport,"screenshot":screenshot,
            "summary":summary,"elements":snapshot["elements"],"interactions":hover,
            "responsive_probes":probes}
    schema=json.loads(files("site_transfer").joinpath("resources","design-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)
    return report
