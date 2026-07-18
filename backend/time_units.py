from __future__ import annotations


BLOCK_HOURS = 0.5


def hours_to_blocks(hours: float) -> int:
    if not isinstance(hours, (int, float)):
        raise ValueError("hours must be numeric")
    if hours <= 0:
        raise ValueError("hours must be > 0")

    blocks = round(float(hours) / BLOCK_HOURS)
    if abs((blocks * BLOCK_HOURS) - float(hours)) > 1e-9:
        raise ValueError("hours must be a multiple of 0.5")
    return int(blocks)


def blocks_to_hours(blocks: int) -> float:
    if not isinstance(blocks, int):
        raise ValueError("blocks must be an integer")
    if blocks <= 0:
        raise ValueError("blocks must be > 0")
    return blocks * BLOCK_HOURS
