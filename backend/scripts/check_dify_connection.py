from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.dify.client import DifyClient
from app.dify.workflow_spec import INPUT_VARIABLES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Dify workflow connectivity and compare input variables.")
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Print the raw /parameters response for debugging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = DifyClient()
    parameters, status = client.get_workflow_parameters()

    print(f"Status: {status}")
    if status == "skipped":
        print("Dify is not configured yet. Fill DIFY_API_KEY and DIFY_BASE_URL after the workflow is deployed.")
        return 0

    if status == "error":
        print(json.dumps(parameters, ensure_ascii=False, indent=2))
        return 1

    dify_variables = extract_variable_names(parameters)
    missing_in_dify = [name for name in INPUT_VARIABLES if name not in dify_variables]
    extra_in_dify = [name for name in dify_variables if name not in INPUT_VARIABLES]

    print(f"Expected input variables: {len(INPUT_VARIABLES)}")
    print(f"Dify input variables:     {len(dify_variables)}")
    print(f"Missing in Dify:          {missing_in_dify or 'none'}")
    print(f"Extra in Dify:            {extra_in_dify or 'none'}")

    if args.show_raw:
        print(json.dumps(parameters, ensure_ascii=False, indent=2))

    return 0 if not missing_in_dify else 1


def extract_variable_names(parameters: dict) -> list[str]:
    variable_names: list[str] = []
    for key in ("user_input_form", "opening_statement_variables", "inputs"):
        entries = parameters.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            direct_name = entry.get("variable") or entry.get("name")
            if isinstance(direct_name, str) and direct_name not in variable_names:
                variable_names.append(direct_name)
                continue

            # Dify commonly nests each form item under its input type, e.g.
            # {"text-input": {"variable": "user_id", ...}}
            for nested in entry.values():
                if not isinstance(nested, dict):
                    continue
                nested_name = nested.get("variable") or nested.get("name")
                if isinstance(nested_name, str) and nested_name not in variable_names:
                    variable_names.append(nested_name)
    return variable_names


if __name__ == "__main__":
    raise SystemExit(main())
