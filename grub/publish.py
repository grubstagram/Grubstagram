"""Publish a carousel through the Instagram API with Instagram Login (graph.instagram.com).

Flow: one container per image (is_carousel_item) -> carousel container -> wait FINISHED -> media_publish.
Instagram downloads each image from a public URL, so slides must be pushed before this runs.
"""
import time

import httpx

from . import env


class IG:
    def __init__(self, cfg: dict):
        icfg = cfg["instagram"]
        self.base = f"https://graph.instagram.com/{icfg['api_version']}"
        self.user = env("IG_USER_ID", required=False) or icfg["user_id"]
        self.token = env("IG_ACCESS_TOKEN")
        self.alt = icfg.get("use_alt_text", False)

    def _req(self, method: str, path: str, **params) -> dict:
        params["access_token"] = self.token
        r = httpx.request(method, f"{self.base}/{path}", params=params if method == "GET" else None,
                          data=params if method == "POST" else None, timeout=120)
        if r.status_code >= 400:
            # Never echo the token back into logs.
            raise RuntimeError(f"Instagram {method} {path} -> {r.status_code}: {r.text[:600]}")
        return r.json()

    def wait(self, container: str, tries: int = 20, delay: int = 15) -> None:
        for _ in range(tries):
            status = self._req("GET", container, fields="status_code").get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Container {container} status {status}")
            time.sleep(delay)
        raise RuntimeError(f"Container {container} not ready after {tries * delay}s")

    def carousel(self, image_urls: list[str], caption: str, alt_text: str = "", log=print) -> dict:
        children = []
        for i, url in enumerate(image_urls):
            params = {"image_url": url, "is_carousel_item": "true"}
            if self.alt and alt_text and i == 0:
                params["alt_text"] = alt_text
            cid = self._req("POST", f"{self.user}/media", **params)["id"]
            log(f"  child {i + 1}/{len(image_urls)} container {cid}")
            children.append(cid)
        for cid in children:
            self.wait(cid)
        parent = self._req("POST", f"{self.user}/media", media_type="CAROUSEL",
                           children=",".join(children), caption=caption)["id"]
        self.wait(parent)
        media_id = self._req("POST", f"{self.user}/media_publish", creation_id=parent)["id"]
        info = self._req("GET", media_id, fields="permalink,timestamp")
        return {"media_id": media_id, **info}

    def limit(self) -> dict:
        return self._req("GET", f"{self.user}/content_publishing_limit", fields="quota_usage,config")


def refresh_token(cfg: dict) -> str:
    """Long-lived tokens last 60 days; refreshing (once the token is 24h+ old) resets the clock."""
    r = httpx.get("https://graph.instagram.com/refresh_access_token",
                  params={"grant_type": "ig_refresh_token", "access_token": env("IG_ACCESS_TOKEN")}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Token refresh failed {r.status_code}: {r.text[:300]}")
    return r.json()["access_token"]
