import re, typing as t

import requests


class Imgur:
    def __init__(self, client_id: str, session: requests.Session = None):
        self.client_id = client_id
        # self.client_secret = client_secret
        self.session = session or requests.Session()

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Client-ID {self.client_id}"}

    def get_image_urls(self, url: str) -> t.Union[str, list[str]]:
        if match := re.fullmatch(r".*?/a/([a-z0-9]+)(?:\.[a-z0-9]+)?", url, re.IGNORECASE):
            return self._get_album_image_urls(match[1])

        if match := re.fullmatch(r".*?/t/[^/]+/([a-z0-9]+)(?:\.[a-z0-9]+)?", url, re.IGNORECASE):
            return self._get_album_image_urls(match[1])

        if match := re.fullmatch(r".*?/([a-z0-9]+)(?:\.[a-z0-9]+)?", url, re.IGNORECASE):
            return self._get_single_image_url(match[1])

        raise ValueError(f"Unable to parse Imgur URL {url!r}")

    def _get_single_image_url(self, hash: str) -> str:
        resp = self.session.get(f"https://api.imgur.com/3/image/{hash}", headers=self.headers)
        self._raise_for_error(resp)

        return resp.json()["data"]["link"]

    def _get_album_image_urls(self, hash: str) -> list[str]:
        resp = self.session.get(f"https://api.imgur.com/3/album/{hash}", headers=self.headers)
        self._raise_for_error(resp)

        return [x["link"] for x in resp.json()["data"]["images"]]

    @staticmethod
    def _raise_for_error(response: requests.Response):
        response.raise_for_status()

        json = response.json()

        if json["success"] is not True:
            status = json["status"]
            error = json["data"].get("error")
            if error is None:
                raise ValueError(f"Error {status}")
            raise ValueError(f"Error {status}: {error}")
