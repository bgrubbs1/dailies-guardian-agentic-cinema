# Third-party software notices

Dailies Guardian's original source, documentation, static interface, synthetic
fixtures, and integration configuration are distributed under the repository's
MIT license. That license does not relicense the following third-party work.

| Component | Pinned version | License | Use |
| --- | ---: | --- | --- |
| [Google Agent Development Kit](https://github.com/google/adk-python) | 2.6.3 | Apache-2.0 | Gemini agent runtime |
| [FastAPI](https://github.com/fastapi/fastapi) | 0.141.1 | MIT | HTTP application |
| [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk) | 1.29.0 | MIT | MCP client transport |
| [Pydantic](https://github.com/pydantic/pydantic) | 2.13.4 | MIT | Request and configuration models |
| [Uvicorn](https://github.com/encode/uvicorn) | 0.52.1 | BSD-3-Clause | ASGI server |
| [Grafana MCP](https://github.com/grafana/mcp-grafana/tree/v1.0.0) | 1.0.0 | Apache-2.0 | Official read-only Grafana tools |

`requirements.lock` records the complete resolved Python runtime set used by
the verified Linux container. Installed distributions retain their own license
metadata. The container build copies Grafana MCP's upstream Apache-2.0 license
from the pinned Go module into `/usr/share/licenses/mcp-grafana/LICENSE` beside
the redistributed binary.

The multi-stage build uses the official `golang:1.26.3-bookworm` builder and
`python:3.12-slim` runtime images. Their operating-system and language packages
remain under their respective upstream licenses. The separate Grafana and Loki
images referenced by local smoke-test scripts are pulled by digest for testing;
they are not copied into this repository or the Dailies Guardian runtime image.

Google, Gemini, Grafana, Loki, and other product names are used only to identify
interoperability. Their trademarks and logos are not licensed by this project.
