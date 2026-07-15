"""Contratos del runner de pruebas reales, sin llamar a la API."""

from __future__ import annotations

import pytest

from fire_test.run_natural import reject_chromium_blocked_video_sources


def _video_payload(url):
  return [{
      "version": "v0.9",
      "updateComponents": {
          "surfaceId": "product",
          "components": [{"id": "video", "component": "Video", "url": url}],
      },
  }]


def test_fire_test_allows_a_direct_video_url():
  reject_chromium_blocked_video_sources(
      _video_payload("https://www.w3schools.com/html/mov_bbb.mp4")
  )


@pytest.mark.parametrize(
    "url, error",
    [
        (
            "https://storage.googleapis.com/gtv-videos-bucket/sample/video.mp4",
            "Google Storage",
        ),
        ({"path": "/product/video"}, "MP4 HTTPS literal"),
    ],
)
def test_fire_test_rejects_non_playable_video_sources(url, error):
  with pytest.raises(ValueError, match=error):
    reject_chromium_blocked_video_sources(_video_payload(url))
