import re
from typing import Optional

import requests

EXTRACT_SHARE_URL_FROM_TIKTOK = r'.*(https:\/\/vm.tiktok.com/[^\s^\/]+)'

EXTRACT_TIKTOK_ID_FROM_URL = r'https:\/\/m.tiktok.com\/v\/(.*)\.html'


def get_tiktok_id_by_share_url(share_url: str) -> Optional[str]:
    video_url = requests.get(share_url, allow_redirects=False).headers['Location']

    if m := re.match(EXTRACT_TIKTOK_ID_FROM_URL, video_url):
        return m.group(1)

    return None
