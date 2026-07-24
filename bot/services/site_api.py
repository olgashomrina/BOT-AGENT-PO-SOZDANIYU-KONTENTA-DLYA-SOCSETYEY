from __future__ import annotations

from aiohttp import web

from bot.storage.site_content import get_site_content


def build_site_api_app(db_path: str, media_dir: str) -> web.Application:
    app = web.Application()
    app["db_path"] = db_path
    app.router.add_get("/content/{page}/{block_id}", handle_get_content)
    app.router.add_static("/media/", media_dir, show_index=False)
    return app


async def handle_get_content(request: web.Request) -> web.Response:
    page = request.match_info["page"]
    block_id = request.match_info["block_id"]
    db_path = request.app["db_path"]

    content = get_site_content(db_path, page, block_id)
    if content is None:
        return web.json_response(
            {"error": "not_found"},
            status=404,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    return web.json_response(
        {"text": content.text, "photo_path": content.photo_static_path},
        headers={"Access-Control-Allow-Origin": "*"},
    )
