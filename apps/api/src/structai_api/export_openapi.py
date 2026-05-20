"""Print the FastAPI app's OpenAPI schema to stdout.

Used by `make openapi-gen` so the codegen doesn't need a running server.
"""

from __future__ import annotations

import json

from structai_api.main import app


def main() -> None:
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
