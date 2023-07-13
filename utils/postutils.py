import logging
import time
from typing import Optional

from pythorhead import Lemmy
from pythorhead.types import SortType, ListingType


class PostUtils:

    @staticmethod
    def safe_api_call(fun, **kwargs):
        retries = 1
        while not (response := fun(**kwargs)) and retries < 10:
            retries += 1
            logging.warning(f"Failed to call {fun.__name__}({kwargs}), will retry again in {retries * 5} seconds")
            time.sleep(retries * 5)

        if retries >= 10:
            raise RuntimeError("Failed to invoke Lemmy API")
        else:
            return response

    @staticmethod
    def get_posts_deep(lemmy: Lemmy, community_id: Optional[int] = None,
                       community_name: Optional[str] = None,
                       saved_only: Optional[bool] = None,
                       sort: Optional[SortType] = None,
                       type_: Optional[ListingType] = None):
        posts = []
        for i in range(1, 6):
            response = PostUtils.safe_api_call(lemmy.post.list, community_id=community_id,
                                               community_name=community_name,
                                               sort=sort,
                                               type_=type_, page=i)

            # ugly hack since there are very few saved pages....
            if saved_only:
                posts.extend([post['post'] for post in response if not post['post']["deleted"] and post['saved']])
            else:
                posts.extend([post['post'] for post in response if not post['post']["deleted"]])
        return posts
