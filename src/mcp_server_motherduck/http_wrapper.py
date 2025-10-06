import json
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.requests import Request
from starlette.routing import Mount

from mcp.server.sse import create_sse_app
from .server import build_application

# Costruisci l'app SSE originale
server, _ = build_application(
    db_path="md:",
)
sse_app = create_sse_app(server)

async def _receive_with(body: bytes):
    sent = False
    async def _recv():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}
    return _recv

async def router(scope, receive, send):
    # Health check su "/" => 200
    if scope["type"] == "http" and scope["path"] == "/" and scope["method"] in {"GET","HEAD"}:
        resp = PlainTextResponse("ok")
        return await resp(scope, receive, send)

    # Alcuni client fanno POST /sse; alias a "/" se la tua versione lo richiede
    if scope["type"] == "http" and scope["path"] == "/sse" and scope["method"] == "POST":
        # rileggi body e inoltra all'app SSE cambiando il path
        req = Request(scope, receive=receive)
        body = await req.body()
        scope = dict(scope)
        scope["path"] = "/"          # alias
        receive = await _receive_with(body)
        return await sse_app(scope, receive, send)

    # Tutto il resto lo gestisce l'app SSE (GET /sse compreso)
    return await sse_app(scope, receive, send)

app = Starlette(routes=[Mount("/", router)])
