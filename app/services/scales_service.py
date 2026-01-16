from __future__ import annotations

import copy
import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Dict, Tuple, Optional
from typing import Iterator


from scales.exceptions import DeviceError
from ..integrations.mertech import get_scales
from sqlalchemy.orm import Session

from .products_cache_service import load_cached_products, save_cached_products
from ..config import settings
from ..models import Device

logger = logging.getLogger("app.scales_client")


@contextmanager
def _timed(op: str, **fields: Any) -> Iterator[None]:
    """
    Контекстный менеджер для логирования операции с измерением длительности.
    """
    start = time.perf_counter()
    logger.info("start %s | %s", op, fields)
    try:
        yield
        dur_ms = int((time.perf_counter() - start) * 1000)
        logger.info("success %s | duration_ms=%s | %s", op, dur_ms, fields)
    except Exception:
        dur_ms = int((time.perf_counter() - start) * 1000)
        logger.exception("fail %s | duration_ms=%s | %s", op, dur_ms, fields)
        raise


def validate_plu_uniqueness(products: dict) -> None:
    items = products.get("products", [])
    if not isinstance(items, list):
        raise DeviceError("Некорректный формат: поле products должно быть массивом.")

    seen = set()
    for p in items:
        if not isinstance(p, dict):
            continue
        if "pluNumber" not in p:
            continue
        key = str(p["pluNumber"])
        if key in seen:
            raise DeviceError(
                f"Нарушение уникальности pluNumber в рамках устройства: pluNumber={key}"
            )
        seen.add(key)


def fetch_products_and_cache(db: Session, device: Device) -> dict:
    device_id = getattr(device, "id", None)
    fields = {
        "device_id": device_id,
        "ip": device.ip,
        "port": device.port,
        "protocol": device.protocol,
    }

    with _timed("scales.fetch_products_and_cache", **fields):
        scales = get_scales(device)

        logger.info(
            "fetch products from scales | device_id=%s | ip=%s | port=%s | protocol=%s",
            device_id,
            device.ip,
            device.port,
            device.protocol,
        )

        products = scales.get_products_json()

        products_count = (
            len(products.get("products", [])) if isinstance(products, dict) else "n/a"
        )
        logger.info(
            "fetch products result | device_id=%s | count=%s",
            device_id,
            products_count,
        )

        validate_plu_uniqueness(products)
        save_cached_products(db, device, products, dirty=False)
        return products


def push_cache_to_scales(db: Session, device: Device) -> None:
    device_id = getattr(device, "id", None)
    fields = {
        "device_id": device_id,
        "ip": device.ip,
        "port": device.port,
        "protocol": device.protocol,
    }

    with _timed("scales.push_cache_to_scales", **fields):
        if not device.products_cache_json:
            logger.warning(
                "push cache skipped | device_id=%s | reason=no_cache", device_id
            )
            raise DeviceError(
                "Нет кэша товаров для загрузки. Сначала выполните выгрузку товаров с весов."
            )

        scales = get_scales(device)
        products = load_cached_products(device)

        products_count = (
            len(products.get("products", [])) if isinstance(products, dict) else "n/a"
        )
        logger.info(
            "push cache to scales | device_id=%s | count=%s | cached_dirty=%s",
            device_id,
            products_count,
            getattr(device, "cached_dirty", None),
        )

        validate_plu_uniqueness(products)

        try:
            scales.send_json_products(products)
        except DeviceError as e:
            if settings.products_fix_mode:
                logger.warning(
                    "bulk upload failed | switching to diagnostic mode | device_id=%s | err=%s",
                    device_id,
                    str(e),
                )
                diagnose_broken_product(device, products)
                raise
            else:
                logger.warning(
                    "bulk upload failed | products fix mode = false | device_id=%s | err=%s",
                    device_id,
                    str(e),
                )
                raise

        device.cached_dirty = False
        db.add(device)
        db.commit()
        db.refresh(device)

        logger.info(
            "push cache completed | device_id=%s | cached_dirty=%s",
            device_id,
            device.cached_dirty,
        )


def diagnose_broken_product(device: Device, products_payload: dict) -> None:
    """
    Диагностический режим загрузки товаров:
    сохраняет структуру payload, меняется только список products.
    Для каждого теста создаёт новый Scales-клиент, чтобы не тащить состояние сокета
    после предыдущей ошибки/порции.
    """
    items = products_payload.get("products", [])
    if not isinstance(items, list):
        raise DeviceError("Некорректный формат: поле products должно быть массивом.")

    logger.warning(
        "diagnostic mode started | device_id=%s | total_products=%s",
        getattr(device, "id", None),
        len(items),
    )

    # Шаблон: весь payload как есть без товаров
    template = copy.deepcopy(products_payload)
    template["products"] = []

    for idx, item in enumerate(items, start=1):
        plu = item.get("pluNumber")
        name = item.get("name")

        # Собираем payload той же структуры, что и основной, но с 1 товаром
        single_payload = copy.deepcopy(template)
        single_payload["products"] = [item]

        try:
            logger.info(
                "diagnostic upload attempt | index=%s | pluNumber=%s | name=%s",
                idx,
                plu,
                name,
            )

            # Новый клиент на каждую попытку (важно!)
            scales = get_scales(device)

            scales.send_json_products(single_payload)

            logger.info("diagnostic upload OK | index=%s | pluNumber=%s", idx, plu)

        except Exception as e:
            logger.error(
                "BROKEN PRODUCT FOUND | index=%s | pluNumber=%s | name=%s | error=%s",
                idx,
                plu,
                name,
                str(e),
            )
            logger.error(
                "BROKEN PRODUCT FULL DATA | %s", json.dumps(item, ensure_ascii=False)
            )
            raise DeviceError(
                f"Найден проблемный товар: index={idx}, pluNumber={plu}, name={name}"
            ) from e

    logger.warning(
        "diagnostic mode finished | device_id=%s | no broken products found",
        getattr(device, "id", None),
    )


@dataclass
class ProductRef:
    plu: str
    code: str
    name: str

    @staticmethod
    def from_item(item: Dict[str, Any]) -> "ProductRef":
        return ProductRef(
            plu=str(item.get("pluNumber", "")),
            code=str(item.get("code", "")),
            name=str(item.get("name", "")),
        )


@dataclass
class FindBadProductsResult:
    ok_count: int
    total_count: int
    bad_items: List[Dict[str, Any]]
    minimal_failing_groups: List[List[Dict[str, Any]]]


def _chunks(items: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _build_payload_with_products(
    template_payload: Dict[str, Any], products_subset: List[Dict[str, Any]]
) -> Dict[str, Any]:
    payload = copy.deepcopy(template_payload)
    payload["products"] = products_subset
    return payload


def _try_upload_payload(
    upload_fn: Callable[[Dict[str, Any]], None],
    payload: Dict[str, Any],
    *,
    label: str,
    timeout_hint_sec: float = 0.0,
) -> Tuple[bool, Optional[Exception]]:
    """
    upload_fn(payload) должен выбросить исключение при ошибке (DeviceError/Exception),
    либо завершиться без исключений при успехе.
    """
    started = time.perf_counter()
    try:
        upload_fn(payload)
        dur_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "upload OK | %s | duration_ms=%s | count=%s",
            label,
            dur_ms,
            len(payload.get("products", [])),
        )
        return True, None
    except Exception as e:
        dur_ms = int((time.perf_counter() - started) * 1000)
        logger.error(
            "upload FAIL | %s | duration_ms=%s | count=%s | err=%r",
            label,
            dur_ms,
            len(payload.get("products", [])),
            e,
        )
        if timeout_hint_sec:
            time.sleep(timeout_hint_sec)
        return False, e


def _bisect_find_minimal_failing_group(
    upload_fn: Callable[[Dict[str, Any]], None],
    template_payload: Dict[str, Any],
    group: List[Dict[str, Any]],
    *,
    label_prefix: str,
) -> List[Dict[str, Any]]:
    """
    Возвращает минимальную подгруппу товаров, которая все еще падает при загрузке.
    Если по одному товару не падает, но в комбинации падает — вернет минимальную "комбинацию".
    """
    # Базовый случай
    if len(group) <= 1:
        return group

    mid = len(group) // 2
    left = group[:mid]
    right = group[mid:]

    left_payload = _build_payload_with_products(template_payload, left)
    ok_left, _ = _try_upload_payload(
        upload_fn, left_payload, label=f"{label_prefix}/L({len(left)})"
    )

    if not ok_left:
        return _bisect_find_minimal_failing_group(
            upload_fn, template_payload, left, label_prefix=label_prefix + "/L"
        )

    right_payload = _build_payload_with_products(template_payload, right)
    ok_right, _ = _try_upload_payload(
        upload_fn, right_payload, label=f"{label_prefix}/R({len(right)})"
    )

    if not ok_right:
        return _bisect_find_minimal_failing_group(
            upload_fn, template_payload, right, label_prefix=label_prefix + "/R"
        )

    # Если обе половины по отдельности проходят, но исходная группа падала — значит проблема комбинационная.
    failing_combo: List[Dict[str, Any]] = []
    base: List[Dict[str, Any]] = []

    # Начнем с одного элемента слева и будем добавлять элементы справа, пока не упадет.
    base = [left[0]]
    for item in right:
        candidate = base + [item]
        cand_payload = _build_payload_with_products(template_payload, candidate)
        ok, _ = _try_upload_payload(
            upload_fn, cand_payload, label=f"{label_prefix}/COMBO({len(candidate)})"
        )
        if not ok:
            failing_combo = candidate
            break

    if failing_combo:
        # Уточняем минимальность уже для комбинации
        return _bisect_find_minimal_failing_group(
            upload_fn, template_payload, failing_combo, label_prefix=label_prefix + "/C"
        )

    # Если не нашли — возвращаем исходную группу
    return group


def find_products_breaking_upload(
    upload_fn: Callable[[Dict[str, Any]], None],
    full_payload: Dict[str, Any],
    *,
    initial_chunk_size: int = 50,
    max_chunk_size: int = 500,
    raise_on_empty_products: bool = True,
) -> FindBadProductsResult:
    """
    Главная функция.

    Функция, которая отправляет payload в весы и бросает исключение при неудаче

    full_payload: JSON (как в ProductData.json), где есть ключ "products": [...] :contentReference[oaicite:1]{index=1}

    Алгоритм:
      1) Идём пачками, чтобы быстро локализовать проблемный сегмент.
      2) Для каждой упавшей пачки — бинарно сужаем до минимальной падающей группы.
      3) Проверяем элементы по одному, чтобы выделить проблемные товары.
    """
    if "products" not in full_payload or not isinstance(full_payload["products"], list):
        if raise_on_empty_products:
            raise ValueError('Payload must contain list field "products"')
        return FindBadProductsResult(
            ok_count=0, total_count=0, bad_items=[], minimal_failing_groups=[]
        )

    template_payload = copy.deepcopy(full_payload)
    template_payload["products"] = []

    items: List[Dict[str, Any]] = full_payload["products"]
    total = len(items)

    logger.info("find_products_breaking_upload: total products=%s", total)

    # 1) Найдем максимально большой размер пачки, который вообще проходит (адаптивно).
    chunk_size = max(1, initial_chunk_size)
    ok_count = 0

    bad_items: List[Dict[str, Any]] = []
    minimal_failing_groups: List[List[Dict[str, Any]]] = []

    idx = 0
    while idx < total:
        current_chunk = items[idx : min(total, idx + chunk_size)]
        payload = _build_payload_with_products(template_payload, current_chunk)

        label = f"chunk idx={idx} size={len(current_chunk)}"
        ok, _ = _try_upload_payload(upload_fn, payload, label=label)

        if ok:
            ok_count += len(current_chunk)
            idx += len(current_chunk)

            # пробуем увеличить пачку, чтобы быстрее пройти файл (но не бесконечно)
            if chunk_size < max_chunk_size:
                chunk_size = min(max_chunk_size, chunk_size * 2)
            continue

        # если упало — уменьшаем размер пачки (но не ниже 1)
        if len(current_chunk) > 1:
            failing_group = _bisect_find_minimal_failing_group(
                upload_fn,
                template_payload,
                current_chunk,
                label_prefix=f"bisect idx={idx} size={len(current_chunk)}",
            )
            minimal_failing_groups.append(failing_group)

            # теперь проверим каждый элемент failing_group по одному
            for it in failing_group:
                single_payload = _build_payload_with_products(template_payload, [it])
                ref = ProductRef.from_item(it)
                ok_single, _ = _try_upload_payload(
                    upload_fn,
                    single_payload,
                    label=f"single plu={ref.plu} code={ref.code} name={ref.name[:40]}",
                )
                if not ok_single:
                    bad_items.append(it)

            # чтобы не зациклиться — сдвигаемся вперед на размер failing_group,
            # а chunk_size сбрасываем на поменьше.
            idx += len(current_chunk)
            chunk_size = max(1, initial_chunk_size)
        else:
            # упал одиночный товар
            bad_items.append(current_chunk[0])
            idx += 1
            chunk_size = max(1, initial_chunk_size)

    return FindBadProductsResult(
        ok_count=ok_count,
        total_count=total,
        bad_items=bad_items,
        minimal_failing_groups=minimal_failing_groups,
    )


def load_payload_from_file(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def print_bad_products_report(res: FindBadProductsResult) -> None:
    print(f"OK uploaded (estimated): {res.ok_count}/{res.total_count}")
    print(f"Bad items (fail as single): {len(res.bad_items)}")
    for i, it in enumerate(res.bad_items, 1):
        ref = ProductRef.from_item(it)
        print(f"{i:03d}. plu={ref.plu} code={ref.code} name={ref.name}")

    print(f"\nMinimal failing groups: {len(res.minimal_failing_groups)}")
    for gi, grp in enumerate(res.minimal_failing_groups, 1):
        print(f"\nGroup #{gi} size={len(grp)}")
        for it in grp:
            ref = ProductRef.from_item(it)
            print(f" - plu={ref.plu} code={ref.code} name={ref.name}")
