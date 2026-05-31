import os
from flask import Blueprint, Response

bp = Blueprint("docs", __name__)


@bp.get("/openapi.yaml")
def openapi_yaml():
    # Robustly resolve the file relative to this module
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    spec_path = os.path.join(base_dir, "openapi.yaml")
    if not os.path.exists(spec_path):
        return Response("openapi.yaml not found", status=404)
    with open(spec_path, "rb") as f:
        data = f.read()
    return Response(data, mimetype="application/yaml")


@bp.get("/ui")
def swagger_ui():
    # Minimal Swagger UI via CDN that points to our YAML
    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>FinMind API Docs</title>
        <link rel="stylesheet"
              href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
        <style>body { margin: 0; } #swagger-ui { height: 100vh; }</style>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script>
        window.ui = SwaggerUIBundle({
            url: '/docs/openapi.yaml',
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis],
            layout: 'BaseLayout'
        });
        </script>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")
