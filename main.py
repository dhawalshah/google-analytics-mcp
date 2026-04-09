"""
Google Analytics MCP Server - multi-user version with FastAPI wrapper.
"""

import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from server import mcp
from oauth.auth_routes import router as auth_router
from oauth.google_auth import current_user_email

BASE_URL = os.environ.get("BASE_URL", "")
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "dev-secret-change-me")

mcp_asgi_app = mcp.http_app(path="/")
app = FastAPI(lifespan=mcp_asgi_app.lifespan, redirect_slashes=False)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)
app.include_router(auth_router, prefix="/auth")


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_protected_resource():
    return JSONResponse({"resource": BASE_URL, "authorization_servers": []})


@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/auth/login",
        "token_endpoint": f"{BASE_URL}/auth/token",
        "registration_endpoint": f"{BASE_URL}/register",
    })


@app.post("/register")
async def register():
    return JSONResponse({"client_id": "claude", "client_secret": ""})


@app.middleware("http")
async def require_login_for_mcp(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        email = request.query_params.get("user")
        if not email:
            email = request.session.get("user_email")
        if not email:
            return Response("Unauthorized. Visit /auth/login first.", status_code=401)
        current_user_email.set(email)
    return await call_next(request)


app.mount("/mcp", mcp_asgi_app)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)