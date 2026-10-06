"""Serve known SPA documents without rewriting missing APIs or assets."""
import re

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


_DOCUMENT_ROUTE = re.compile(
    r"(?:dashboard|projects(?:/[A-Za-z0-9_-]+)?|jobs/[A-Za-z0-9_-]+|history|assets|backups|settings)/?"
)


class FrontendStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if (exc.status_code == 404 and scope["method"] in {"GET", "HEAD"}
                    and _DOCUMENT_ROUTE.fullmatch(path.replace("\\", "/"))):
                return await super().get_response("index.html", scope)
            raise
