#
# Brekel Shuffle Helper for ComfyUI
#
# Author: Brekel - https://brekel.com
#
# Turns a seed or index into a pick from a list without the near repeats of plain random picks.
# The seed is treated as a position in an endless series of shuffled passes over the list, so
# consecutive seeds (control set to "increment") visit every item once before any item repeats.
# Each pass is shuffled differently, and where one pass meets the next the items are kept apart
# too, so no item comes up twice within MIN_GAP consecutive seeds (shorter lists, see MIN_GAP).
# The result depends on nothing but the arguments, so the same seed always gives the same pick.


import random


# No item repeats within this many consecutive seeds. Lists under 3 * (MIN_GAP - 1) items keep repeats
# at least a third of their length apart instead, a short list cannot keep every item this far apart.
MIN_GAP = 5


def _pass_order(count: int, pass_number: int, salt: str):
    """The shuffled order of one pass. A string seed is hashed with sha512, so it is stable across runs."""
    order = list(range(count))
    random.Random(f"{salt}:{pass_number}").shuffle(order)
    return order


def shuffled_index(seed: int, count: int, salt: str = "") -> int:
    """
    Returns an index in [0, count) for the given seed.
    Lists with a different salt get unrelated orders, so pass something that identifies the list
    (file name, folder path) to keep several lists driven by the same seed from moving in lockstep.
    """
    # Too short to shuffle without risking the same item twice in a row where passes meet, alternate instead.
    if count < 3:
        return seed % count

    pass_number, position = divmod(seed, count)
    order = _pass_order(count, pass_number, salt)

    # Swap the items that ended the previous pass out of the start of this pass, using spares from the
    # middle. The end of a pass is never touched, so the previous pass's end is just its raw shuffle.
    edge = min(MIN_GAP - 1, count // 3)
    if edge and pass_number > 0:
        previous_end = set(_pass_order(count, pass_number - 1, salt)[-edge:])
        spares = (j for j in range(edge, count - edge) if order[j] not in previous_end)
        for i in range(edge):
            if order[i] in previous_end:
                j = next(spares)
                order[i], order[j] = order[j], order[i]

    return order[position]
