# auth.py -- one shared password for the whole site (HTTP Basic: any username). Needed before the app is online.
import base64
import hmac

from fastapi.responses import Response


class BasicAuth:
    """Pure ASGI middleware (no BaseHTTPMiddleware: it interferes with streaming responses)."""
    def __init__(self, app, password):
        self.app, self.password = app, password.encode()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] == '/api/health':        # health stays open for the container check
            return await self.app(scope, receive, send)
        header = dict(scope['headers']).get(b'authorization', b'').decode()
        ok = False
        if header.lower().startswith('basic '):
            try:
                ok = hmac.compare_digest(base64.b64decode(header[6:]).split(b':', 1)[1], self.password)
            except Exception:
                ok = False
        if ok:
            return await self.app(scope, receive, send)
        await Response('Login required', status_code=401, headers={'WWW-Authenticate': 'Basic realm="NeuraDocs"'})(scope, receive, send)
