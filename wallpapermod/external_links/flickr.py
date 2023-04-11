import re, typing as t

import requests


class Flickr:
    def __init__(self, config: dict, session: requests.Session = None):
        self.config = config
        self.session = session or requests.Session()

    def get_image_urls(self, url: str) -> t.Union[str, list[str]]:
        if match := re.fullmatch(r".*?/photos/[@a-z0-9]+/(\d+)/?", url, re.IGNORECASE):
            return self._get_single_image_url(match[1])

        raise ValueError(f"Unable to parse Flickr URL {url!r}")

    def _get_single_image_url(self, photo_id: str) -> str:
        params = {
            "method": "flickr.photos.getSizes",
            "api_key": self.config["flickr"]["key"],
            "photo_id": photo_id,
            "format": "json",
            "nojsoncallback": 1,
        }
        resp = self.session.get(f"https://www.flickr.com/services/rest/", params=params)
        self._raise_for_error(resp)

        data = resp.json()
        sizelist = data["sizes"]["size"]
        sizelabel = "Original"

        for sizedef in filter(lambda x: x["label"] == sizelabel, sizelist):
            return sizedef["source"]
        else:
            raise ValueError(
                f"No size definition found for label {sizelabel!r} of photo with ID {photo_id}"
            )

    @staticmethod
    def _raise_for_error(response: requests.Response):
        json = response.json()

        if json["stat"] != "ok":
            code = json["code"]
            error = json["message"]
            raise ValueError(f"Error {code}: {error}")
