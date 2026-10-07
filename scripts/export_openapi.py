#!/usr/bin/env python3
"""Print the dashboard FastAPI OpenAPI schema as JSON.

Used by the frontend build to generate a typed API client
(``npm run gen:api`` -> ``openapi-typescript``). Importing the app avoids
needing a running server or a network call.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.dashboard.app import create_app  # noqa: E402


def main() -> None:
    json.dump(create_app().openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
