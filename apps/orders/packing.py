"""Build parcels from measured arrangements or verified automatic packing inputs.

A recipe describes one physically assembled parcel with an exact product count.
Explicit test-only recipes allow fictional examples only against CDEK's sandbox
and remain unconfirmed in every stored packing plan.
Search ranks complete measured plans using parcel count, carrier-rounded volume
and gross weight. Checkout compares a bounded, diverse set using carrier prices;
it does not claim a global minimum across every possible packing arrangement.
Automatic products use explicit non-overlapping placements, not aggregate volume.
"""

from copy import deepcopy
from decimal import Decimal
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q

from .cdek import DeliveryUnavailable, _weight_limits
from .models import PackingBox, PackingRecipe, PackingRecipeItem
from .packaging_models import BOX_PHYSICAL_FIELDS, RECIPE_PHYSICAL_FIELDS, UNIT_PHYSICAL_FIELDS
from .automatic_packing import AutomaticPacking, cart_configuration


PLAN_VERSION = 3
MAX_CART_UNITS = 100
MAX_SEARCH_STATES = 50_000
MAX_SEARCH_ATTEMPTS = 250_000
MAX_SEARCH_SCORES = 1_000_000
MAX_CANDIDATE_RECIPES = 5_000
MAX_PACKING_OPTIONS = 8
PACKAGE_FIELDS = ("package_weight_g", "package_length_cm", "package_width_cm", "package_height_cm")
AXES = ("length", "width", "height")
PRODUCT_CONFIGURATION_FIELDS = (
    "id",
    "name",
    "sku",
    "shipping_mode",
    "unit_weight_g",
    "unit_length_mm",
    "unit_width_mm",
    "unit_height_mm",
    *PACKAGE_FIELDS,
    "package_measurement_signature",
    "package_measured_at",
)
PICKUP_WEIGHT_MESSAGE = (
    "Этот пункт не принимает доступные варианты упаковки заказа по весу. "
    "Выберите другой пункт или свяжитесь с магазином."
)


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _content(product, quantity):
    return {"product_id": product.pk, "sku": product.sku, "name": product.name, "quantity": quantity}


def _package(parcel):
    # CDEK expects whole centimetres; rounding down would understate the parcel.
    return {
        "weight": parcel["weight_g"],
        **{axis: (parcel["dimensions_mm"][axis] + 9) // 10 for axis in AXES},
    }


def _fits_weight(weight, limits):
    return limits is None or (weight >= limits[0] and (not limits[1] or weight <= limits[1]))


def _individual_parcels(item, test_mode, limits):
    product = item.product
    values = [getattr(product, field) for field in PACKAGE_FIELDS]
    if not all(_positive_int(value) for value in values):
        raise DeliveryUnavailable(
            f"Для «{product.name}» ещё не настроена упаковка. Расчёт доставки пока недоступен."
        )
    confirmed = product.package_measurements_valid
    if not test_mode and not confirmed:
        raise DeliveryUnavailable(
            f"Для «{product.name}» ещё не подтверждены замеры упаковки. "
            "Свяжитесь с магазином для расчёта доставки."
        )
    if not _fits_weight(values[0], limits):
        raise DeliveryUnavailable(PICKUP_WEIGHT_MESSAGE)
    return [
        {
            "kind": "individual",
            "recipe_id": None,
            "recipe_name": "Индивидуальная упаковка",
            "box_code": "",
            "box_name": "",
            "weight_g": values[0],
            "dimensions_mm": dict(zip(AXES, (value * 10 for value in values[1:]))),
            "contents": [_content(product, 1)],
            "instructions": "Отправить отдельным грузовым местом в измеренной индивидуальной упаковке.",
            "measurements_confirmed": confirmed,
        }
        for _ in range(item.quantity)
    ]


def _recipe_parcel(recipe, rows):
    return {
        "kind": "recipe",
        "recipe_id": recipe.pk,
        "recipe_name": recipe.name,
        "box_code": recipe.box.code,
        "box_name": recipe.box.name,
        # Gross measured weight already includes carton, protection and filler.
        "weight_g": recipe.measured_weight_g,
        "dimensions_mm": {axis: getattr(recipe, f"outer_{axis}_mm") for axis in AXES},
        "contents": [
            _content(row.product, row.quantity) for row in sorted(rows, key=lambda row: row.product_id)
        ],
        "instructions": recipe.instructions,
        "measurements_confirmed": not recipe.test_only,
        "test_only": recipe.test_only,
    }


class _SearchLimit(Exception):
    pass


def _recipe_queryset(items, test_mode):
    """Only compositions that could participate in this exact cart.

    Enabling a draft or changing an ineligible composition makes it appear in
    the next fingerprint. Edits to unrelated or inactive rules do not disturb
    checkout. Filter before the catalogue bound, including quantity constraints.
    """
    quantities = {item.product_id: item.quantity for item in items}
    invalid = ~Q(product_id__in=quantities)
    for product_id, quantity in quantities.items():
        invalid |= Q(product_id=product_id, quantity__gt=quantity)
    foreign_rows = PackingRecipeItem.objects.filter(recipe_id=OuterRef("pk")).filter(invalid)
    recipes = (
        PackingRecipe.objects.filter(active=True, box__active=True, items__product_id__in=quantities)
        .filter(~Exists(foreign_rows))
        .distinct()
        .select_related("box")
        .prefetch_related("items__product")
        .order_by("pk")
    )
    if not test_mode:
        recipes = recipes.filter(test_only=False)
    confirmed = Q(measured_at__isnull=False) & ~Q(measurement_signature="")
    recipes = recipes.filter(confirmed | Q(test_only=True) if test_mode else confirmed)
    return recipes


def _load_candidates(items, test_mode):
    products = {item.product_id: item for item in items}
    product_ids = tuple(sorted(products))
    target = tuple(products[pk].quantity for pk in product_ids)
    candidates = []
    allow_test_recipes = bool(test_mode and getattr(settings, "CDEK_TEST_MODE", False))
    recipes = _recipe_queryset(items, allow_test_recipes)
    # Bound catalogue work as well as search work. Never silently truncate valid options.
    recipes = list(recipes[: MAX_CANDIDATE_RECIPES + 1])
    if len(recipes) > MAX_CANDIDATE_RECIPES:
        raise DeliveryUnavailable("Для этого заказа требуется расчёт упаковки сотрудником магазина.")
    for recipe in recipes:
        rows = list(recipe.items.all())
        counts = {}
        for row in rows:
            if row.product_id not in products or not _positive_int(row.quantity):
                break
            if any(
                getattr(row.product, field) != getattr(products[row.product_id].product, field)
                for field in PRODUCT_CONFIGURATION_FIELDS
            ):
                raise DeliveryUnavailable(
                    "Параметры товаров изменились во время подбора упаковки. Повторите расчёт."
                )
            counts[row.product_id] = counts.get(row.product_id, 0) + row.quantity
        else:
            vector = tuple(counts.get(pk, 0) for pk in product_ids)
            if not any(vector) or any(count > allowed for count, allowed in zip(vector, target)):
                continue
            dimensions = [getattr(recipe, f"outer_{axis}_mm") for axis in AXES]
            if not all(_positive_int(value) for value in [recipe.measured_weight_g, *dimensions]):
                continue
            if recipe.test_only:
                try:
                    # Check structure and physical consistency, but do not claim
                    # that a person has ever assembled or measured this parcel.
                    recipe.validate_measurements(box=recipe.box, rows=rows)
                except (ValidationError, PackingBox.DoesNotExist):
                    continue
            elif not recipe.measurements_valid_for_snapshot(box=recipe.box, rows=rows):
                continue
            volume = ((dimensions[0] + 9) // 10) * ((dimensions[1] + 9) // 10) * ((dimensions[2] + 9) // 10)
            candidates.append(
                (vector, volume, recipe.measured_weight_g, recipe.pk, _recipe_parcel(recipe, rows))
            )

    return target, candidates, _configuration_snapshot(items, recipes)


def _combined_solutions(target, candidates, limits, limit):
    # A light or small recipe may be inadmissible at the selected office. Filter
    # first, so same-composition dominance cannot discard a feasible alternative.
    admissible = [candidate for candidate in candidates if _fits_weight(candidate[2], limits)]
    try:
        results = _ranked_covers(target, admissible, limit)
        if not results and len(admissible) != len(candidates):
            # Distinguish missing measurements from restrictions of this office,
            # including for callers that did not request a generic plan first.
            if _exact_cover(target, candidates) is not None:
                raise DeliveryUnavailable(PICKUP_WEIGHT_MESSAGE)
    except _SearchLimit as exc:
        raise DeliveryUnavailable(
            "Для этого состава заказа требуется подбор упаковки сотрудником магазина. "
            "Свяжитесь с магазином для точного расчёта доставки."
        ) from exc
    if not results:
        raise DeliveryUnavailable(
            "Для этого состава и количества товаров ещё не проверена общая упаковка. "
            "Свяжитесь с магазином для расчёта доставки."
        )
    parcels = {candidate[3]: candidate[4] for candidate in candidates}
    # Each entry is a separate physical parcel even when the recipe repeats.
    return [[deepcopy(parcels[recipe_id]) for recipe_id in result[3]] for result in results]


def _exact_cover(target, candidates):
    # Identical compositions have interchangeable future states. Keep the exact
    # best objective for each; this reduces branching without any approximation.
    by_composition = {}
    for candidate in candidates:
        previous = by_composition.get(candidate[0])
        if previous is None or candidate[1:4] < previous[1:4]:
            by_composition[candidate[0]] = candidate
    candidates = sorted(by_composition.values(), key=lambda candidate: candidate[3])
    by_product = [
        [candidate for candidate in candidates if candidate[0][index]] for index in range(len(target))
    ]
    states = 0
    attempts = 0

    @lru_cache(maxsize=None)
    def solve(remaining):
        nonlocal states, attempts
        states += 1
        if states > MAX_SEARCH_STATES:
            raise _SearchLimit
        if not any(remaining):
            return (0, 0, 0, ())
        # Every complete solution must include a recipe for this product. Choosing
        # the most constrained product avoids exploring permutations of parcels.
        pivot = min((i for i, count in enumerate(remaining) if count), key=lambda i: len(by_product[i]))
        best = None
        for vector, volume, weight, recipe_id, _ in by_product[pivot]:
            attempts += 1
            if attempts > MAX_SEARCH_ATTEMPTS:
                raise _SearchLimit
            rest = tuple(count - used for count, used in zip(remaining, vector))
            if any(count < 0 for count in rest):
                continue
            suffix = solve(rest)
            if suffix is None:
                continue
            score = (
                suffix[0] + 1,
                suffix[1] + volume,
                suffix[2] + weight,
                tuple(sorted((*suffix[3], recipe_id))),
            )
            if best is None or score < best:
                best = score
        return best

    return solve(target)


def package_key(package):
    """Carrier-equivalent physical parcel, regardless of orientation or recipe."""
    return (package["weight"], *sorted(package[axis] for axis in AXES))


def _ranked_covers(target, candidates, limit):
    if limit == 1:
        result = _exact_cover(target, candidates)
        return [result] if result else []
    # Only identical physical parcels with identical contents are interchangeable.
    # A lighter/lower-volume shape can still be rejected by the carrier; retain
    # alternatives instead of scalar dominance by composition.
    equivalent = {}
    for candidate in candidates:
        key = (candidate[0], package_key(_package(candidate[4])))
        if key not in equivalent or candidate[3] < equivalent[key][3]:
            equivalent[key] = candidate
    candidates = sorted(equivalent.values(), key=lambda candidate: candidate[3])
    keys = {row[3]: package_key(_package(row[4])) for row in candidates}
    by_product = [[row for row in candidates if row[0][index]] for index in range(len(target))]
    priorities = ((0, 1, 2), (1, 2, 0), (2, 1, 0))
    states = attempts = scores = 0

    def ranked(rows, priority):
        return sorted(rows, key=lambda row: (*[row[i] for i in priority], row[3]))

    @lru_cache(maxsize=None)
    def solve(remaining):
        nonlocal states, attempts, scores
        states += 1
        if states > MAX_SEARCH_STATES:
            raise _SearchLimit
        if not any(remaining):
            return ((0, 0, 0, ()),)
        pivot = min((i for i, count in enumerate(remaining) if count), key=lambda i: len(by_product[i]))
        solutions = {}
        for vector, volume, weight, recipe_id, _ in by_product[pivot]:
            attempts += 1
            if attempts > MAX_SEARCH_ATTEMPTS:
                raise _SearchLimit
            rest = tuple(count - used for count, used in zip(remaining, vector))
            if any(count < 0 for count in rest):
                continue
            for suffix in solve(rest):
                scores += 1
                if scores > MAX_SEARCH_SCORES:
                    raise _SearchLimit
                ids = tuple(sorted((*suffix[3], recipe_id)))
                score = (suffix[0] + 1, suffix[1] + volume, suffix[2] + weight, ids)
                physical = tuple(sorted(keys[pk] for pk in ids))
                old = solutions.get(physical)
                if old is None or score < old:
                    solutions[physical] = score
        # Retain the exact best K for each additive ordering at every state.
        # Their union is diverse; no carrier cost optimality is implied.
        retained = {}
        for priority in priorities:
            for row in ranked(solutions.values(), priority)[:limit]:
                retained[row[3]] = row
        return tuple(retained.values())

    solutions = solve(target)
    rankings = [ranked(solutions, priority) for priority in priorities]
    selected = {}
    # Round robin prevents many single-parcel variants from starving compact
    # multi-parcel or lighter alternatives from the network comparison budget.
    for index in range(len(solutions)):
        for ranking in rankings:
            row = ranking[index]
            selected.setdefault(row[3], row)
            if len(selected) >= limit:
                return list(selected.values())
    return list(selected.values())


def _plan(parcels):
    return {
        "version": PLAN_VERSION,
        "packages": [_package(parcel) for parcel in parcels],
        "parcels": parcels,
        "measurements_confirmed": all(parcel["measurements_confirmed"] for parcel in parcels),
        "packing_price": str(
            sum((Decimal(parcel.get("packing_price", "0.00")) for parcel in parcels), Decimal("0.00"))
        ),
    }


class PreparedPacking:
    """Request-scoped snapshot; validate related measurements once before I/O.

    Callers must compare quote_data before and after network work. This object
    must never be cached across requests or used as a persisted attestation.
    """

    def __init__(self, cart, *, test_mode=None):
        actual_test_mode = getattr(settings, "CDEK_TEST_MODE", False)
        test_mode = bool(actual_test_mode and (test_mode is None or test_mode))
        items = self.items = list(cart.items.select_related("product").order_by("product_id"))
        if not items:
            raise DeliveryUnavailable("Добавьте товары в корзину перед расчётом доставки.")
        if any(not _positive_int(item.quantity) for item in items):
            raise DeliveryUnavailable("Проверьте количество товаров в корзине и повторите расчёт доставки.")
        if sum(item.quantity for item in items) > MAX_CART_UNITS:
            raise DeliveryUnavailable(
                "Для такого количества товаров свяжитесь с магазином для расчёта доставки."
            )
        self.individual = []
        combined = []
        automatic = []
        for item in items:
            if item.product.shipping_mode == "individual":
                self.individual.extend(_individual_parcels(item, test_mode, None))
            elif item.product.shipping_mode == "combined":
                combined.append(item)
            elif item.product.shipping_mode == "automatic":
                automatic.append(item)
            else:
                raise DeliveryUnavailable(
                    f"Для «{item.product.name}» ещё не настроен способ упаковки. Свяжитесь с магазином."
                )
        if combined:
            self.target, self.candidates, self.configuration = _load_candidates(combined, test_mode)
        else:
            self.target, self.candidates = (), []
            self.configuration = _configuration_snapshot([], [])
        self.automatic = AutomaticPacking(automatic, allow_test=test_mode) if automatic else None
        self.configuration["automatic"] = self.automatic.configuration if self.automatic else None

    def options(self, *, pickup=None, limit=MAX_PACKING_OPTIONS):
        if not _positive_int(limit) or limit > MAX_PACKING_OPTIONS:
            raise ValueError("Invalid packing option limit")
        limits = (
            _weight_limits(pickup.get("weight_min_g"), pickup.get("weight_max_g"))
            if pickup is not None
            else None
        )
        if any(not _fits_weight(parcel["weight_g"], limits) for parcel in self.individual):
            raise DeliveryUnavailable(PICKUP_WEIGHT_MESSAGE)
        combined = _combined_solutions(self.target, self.candidates, limits, limit) if self.target else [[]]
        automatic = self.automatic.options(limits=limits, limit=limit) if self.automatic else [[]]
        plans = [
            _plan(deepcopy(self.individual) + parcels + auto) for parcels in combined for auto in automatic
        ]
        if self.automatic:
            minimum = min(len(plan["packages"]) for plan in plans)
            plans = [plan for plan in plans if len(plan["packages"]) == minimum]
            plans.sort(
                key=lambda p: (
                    sum(k[1] * k[2] * k[3] for k in map(package_key, p["packages"])),
                    sum(pack["weight"] for pack in p["packages"]),
                )
            )
        return plans[:limit]


def packing_options(cart, *, test_mode=None, pickup=None, limit=MAX_PACKING_OPTIONS):
    return PreparedPacking(cart, test_mode=test_mode).options(pickup=pickup, limit=limit)


def packing_plan(cart, *, test_mode=None, pickup=None):
    """Canonical measured plan for display; checkout compares carrier alternatives."""
    return packing_options(cart, test_mode=test_mode, pickup=pickup, limit=1)[0]


def _json_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _model_values(instance):
    return {
        field.attname: _json_value(getattr(instance, field.attname))
        for field in instance._meta.concrete_fields
    }


def _configuration_snapshot(items, loaded_recipes):
    """Pure fingerprint input, also used to bind the actual planner snapshot."""
    recipes, boxes = [], {}
    for recipe in loaded_recipes:
        # Names and timestamps of ordinary saves do not change packing.
        row = {
            field: _json_value(getattr(recipe, field))
            for field in (
                "id",
                "box_id",
                *RECIPE_PHYSICAL_FIELDS,
                "measurement_signature",
                "measured_at",
            )
        }
        row["items"] = [
            {"product_id": item.product_id, "quantity": item.quantity}
            for item in sorted(recipe.items.all(), key=lambda item: item.product_id)
        ]
        recipes.append(row)
        box = recipe.box
        boxes[box.pk] = {field: getattr(box, field) for field in ("id", "code", *BOX_PHYSICAL_FIELDS)}
    return {
        "version": PLAN_VERSION,
        "boxes": [boxes[pk] for pk in sorted(boxes)],
        "recipes": recipes,
        "products": [
            {
                field: getattr(item.product, field)
                for field in ("id", "sku", "shipping_mode", *UNIT_PHYSICAL_FIELDS)
            }
            for item in items
        ],
    }


def packing_configuration(cart=None):
    """Cart-scoped physical dependencies; no-cart form is a full diagnostic dump.

    Ineligible/draft rules are absent from checkout's fingerprint. Enabling them
    or editing their composition to become eligible changes the membership and
    invalidates the quote without hashing unrelated catalogue edits.
    """
    if cart is not None:
        items = list(cart.items.select_related("product").order_by("product_id"))
        if sum(item.quantity for item in items) > MAX_CART_UNITS:
            return {"version": PLAN_VERSION, "limit_exceeded": "cart_units"}
        combined = [item for item in items if item.product.shipping_mode == "combined"]
        recipes = (
            list(
                _recipe_queryset(combined, getattr(settings, "CDEK_TEST_MODE", False))[
                    : MAX_CANDIDATE_RECIPES + 1
                ]
            )
            if combined
            else []
        )
        if len(recipes) > MAX_CANDIDATE_RECIPES:
            # No quote can be issued for this state: PreparedPacking refuses it.
            # A sentinel lets checkout display that actionable error, while
            # bounding fingerprint work and invalidating earlier valid quotes.
            return {"version": PLAN_VERSION, "limit_exceeded": "recipes"}
        result = _configuration_snapshot(combined, recipes)
        automatic = [item for item in items if item.product.shipping_mode == "automatic"]
        result["automatic"] = cart_configuration(automatic, getattr(settings, "CDEK_TEST_MODE", False))
        return result
    recipes = []
    for recipe in PackingRecipe.objects.order_by("pk").prefetch_related("items__product"):
        row = _model_values(recipe)
        row["items"] = [
            {
                **_model_values(item),
                "product": {
                    field: _json_value(getattr(item.product, field)) for field in PRODUCT_CONFIGURATION_FIELDS
                },
            }
            for item in sorted(recipe.items.all(), key=lambda item: (item.product_id, item.pk))
        ]
        recipes.append(row)
    return {
        "version": PLAN_VERSION,
        "boxes": [_model_values(box) for box in PackingBox.objects.order_by("pk")],
        "recipes": recipes,
    }
