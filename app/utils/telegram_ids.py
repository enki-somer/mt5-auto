from __future__ import annotations


def channel_id_variants(chat_id: int) -> set[int]:
    variants = {chat_id}
    as_text = str(chat_id)
    if as_text.startswith("-100") and len(as_text) > 4:
        variants.add(int(as_text[4:]))
    if chat_id > 0:
        variants.add(int(f"-100{chat_id}"))
    return variants


def is_allowed_channel(chat_id: int, allowed: list[int]) -> bool:
    if not allowed:
        return False
    allowed_set: set[int] = set()
    for item in allowed:
        allowed_set.update(channel_id_variants(item))
    return bool(channel_id_variants(chat_id) & allowed_set)
