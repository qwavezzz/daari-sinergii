"""Bounded orthogonal packing with explicit placements, support and load checks.

Items are rectangular envelopes INCLUDING individual protection. We never infer
fit from aggregate volume. This is a conservative search, not a global optimizer.
"""

from itertools import permutations, product
from math import prod
from time import monotonic


class SearchLimit(Exception):
    pass


class Budget:
    def __init__(self, attempts=150_000, seconds=4):
        self.remaining = attempts
        self.deadline = monotonic() + seconds

    def tick(self):
        self.remaining -= 1
        if self.remaining < 0 or monotonic() > self.deadline:
            raise SearchLimit


def orientations(unit):
    dimensions = unit["dimensions"]
    choices = (
        permutations(dimensions)
        if unit["rotate"]
        else (dimensions, (dimensions[1], dimensions[0], dimensions[2]))
    )
    return sorted(set(choices), key=lambda d: (d[2], d[1], d[0]))


def overlap_xy(a, b):
    return all(
        a["pos"][i] < b["pos"][i] + b["size"][i] and b["pos"][i] < a["pos"][i] + a["size"][i] for i in (0, 1)
    )


def admissible(candidate, placed, inner):
    pos, size = candidate["pos"], candidate["size"]
    if any(pos[i] < 0 or pos[i] + size[i] > inner[i] for i in range(3)):
        return False
    for other in placed:
        if all(
            pos[i] < other["pos"][i] + other["size"][i] and other["pos"][i] < pos[i] + size[i]
            for i in range(3)
        ):
            return False
    if pos[2] and not any(
        other["pos"][2] + other["size"][2] == pos[2]
        and all(
            other["pos"][i] <= pos[i] and pos[i] + size[i] <= other["pos"][i] + other["size"][i]
            for i in (0, 1)
        )
        for other in placed
    ):
        return False  # No floating or bridging: the entire base must have support.
    all_units = [*placed, candidate]
    for base in all_units:
        load = sum(
            other["unit"]["weight"]
            for other in all_units
            if other["pos"][2] >= base["pos"][2] + base["size"][2] and overlap_xy(base, other)
        )
        if load > base["unit"]["stack_limit"]:
            return False
    return True


def positions(placed, inner, budget):
    coordinates = [{0}, {0}, {0}]
    for row in placed:
        for axis in range(3):
            coordinates[axis].add(row["pos"][axis])
            edge = row["pos"][axis] + row["size"][axis]
            if edge < inner[axis]:
                coordinates[axis].add(edge)
    for z, y, x in product(sorted(coordinates[2]), sorted(coordinates[1]), sorted(coordinates[0])):
        budget.tick()
        yield (x, y, z)


def ordered(units):
    return sorted(units, key=lambda u: (-prod(u["dimensions"]), -u["weight"], u["product_id"], u["number"]))


def fit_all(units, inner, max_contents_weight, budget):
    if sum(u["weight"] for u in units) > max_contents_weight or sum(
        prod(u["dimensions"]) for u in units
    ) > prod(inner):
        return None
    units = ordered(units)
    if any(
        not any(all(d <= available for d, available in zip(size, inner)) for size in orientations(u))
        for u in units
    ):
        return None
    if all(unit["stack_limit"] == 0 for unit in units):
        # With no load-bearing units, every item must stand on the floor.
        # This cheap necessary bound avoids exponential searches for tall,
        # half-empty boxes whose usable floor is already too small.
        minimum_floor = sum(
            min(
                size[0] * size[1]
                for size in orientations(unit)
                if all(d <= available for d, available in zip(size, inner))
            )
            for unit in units
        )
        if minimum_floor > inner[0] * inner[1]:
            return None
    placed = []

    def search(index):
        budget.tick()
        if index == len(units):
            return list(placed)
        unit = units[index]
        for pos in positions(placed, inner, budget):
            for size in orientations(unit):
                budget.tick()
                candidate = {"unit": unit, "pos": pos, "size": size}
                if admissible(candidate, placed, inner):
                    placed.append(candidate)
                    result = search(index + 1)
                    if result is not None:
                        return result
                    placed.pop()
        return None

    return search(0)


def fit_some(units, inner, max_contents_weight, budget):
    """Construct a valid partial box for splitting after one-box attempts fail."""
    placed = []
    weight = 0
    for unit in ordered(units):
        if weight + unit["weight"] > max_contents_weight:
            continue
        found = None
        for pos in positions(placed, inner, budget):
            for size in orientations(unit):
                budget.tick()
                candidate = {"unit": unit, "pos": pos, "size": size}
                if admissible(candidate, placed, inner):
                    found = candidate
                    break
            if found:
                break
        if found:
            placed.append(found)
            weight += unit["weight"]
    return placed
