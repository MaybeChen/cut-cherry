from functools import lru_cache

@lru_cache(maxsize=16)
def singleton(key: str):
    return None
