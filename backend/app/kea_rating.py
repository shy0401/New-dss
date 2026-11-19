"""한국에너지공단 건축물 에너지효율등급 인증 정보(공공데이터포털 15100521)를 원본 그대로 받는다.

받기만 한다. 응답 쪽(JSON)을 받은 그대로 ``data/raw/kea_building_rating/<받은 날>/pages/`` 에 두고,
건수 · 해시를 ``manifest.json`` 에 적는다. 값을 고치거나 DB에 넣지 않는다(문자 "NULL" 정리 · 주소 맞춤은
다음 단계). 이미 받은 쪽은 건너뛰므로 끊겨도 다시 돌리면 이어 받는다. 인증키는 파일 · 출력에 남기지 않는다.

확인(2026-11-20, 1쪽 호출): 요청 주소 ``BEEC_01_LIST``, ``apiType=json``, 한 쪽 최대 100건,
조건 없이 ``totalCount`` 39,447건, 개발계정 하루 10,000건.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx

URL = "https://apis.data.go.kr/B553530/BEEC/BEEC_01_LIST"
PAGE_SIZE = 100
REQUEST_DELAY_S = 0.2
SOURCE = "한국에너지공단_건축물 에너지 효율등급 정보 (공공데이터포털 15100521)"


class RatingFetchError(RuntimeError):
    pass


def _body(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise RatingFetchError(f"JSON이 아닌 응답: {text[:200]}") from exc
    response = data.get("response") or {}
    header = response.get("header") or {}
    if str(header.get("resultCode")) != "00":
        raise RatingFetchError(f"API 오류 {header.get('resultCode')}: {header.get('resultMsg')}")
    return response.get("body") or {}


def _items(body: dict[str, Any]) -> list[Any]:
    items = (body.get("items") or {}).get("item") or []
    return items if isinstance(items, list) else [items]


def fetch_all(
    out_dir: Path,
    service_key: str,
    client: httpx.Client | None = None,
    page_size: int = PAGE_SIZE,
    delay_s: float = REQUEST_DELAY_S,
    log: Callable[[str], None] = lambda message: None,
) -> dict[str, Any]:
    """Save every page of the list as received. Pages already on disk are not asked again."""
    key = service_key.strip()
    if not key:
        raise RatingFetchError("DATA_GO_KR_SERVICE_KEY 미설정")
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    client = client or httpx.Client(timeout=60)
    calls = 0

    def page_text(page: int) -> str:
        nonlocal calls
        path = pages_dir / f"page-{page:04d}.json"
        if path.exists():
            return path.read_text(encoding="utf-8")
        params = {"serviceKey": key, "pageNo": str(page), "numOfRows": str(page_size), "apiType": "json"}
        # httpx의 오류 문장에는 요청 주소(인증키 포함)가 들어가므로 원래 예외를 잇지 않고(from None) 주소 없이 다시 던진다
        try:
            response = client.get(URL, params=params)
        except httpx.HTTPError as exc:
            raise RatingFetchError(f"{page}쪽 요청 실패: {type(exc).__name__}") from None
        calls += 1
        if response.status_code >= 400:
            raise RatingFetchError(f"{page}쪽 HTTP {response.status_code}")
        text = response.text
        if key in text or quote(key, safe="") in text:
            raise RatingFetchError("응답에 인증키가 들어 있어 저장하지 않음")
        _body(text)  # an error page is not kept as data
        path.write_text(text, encoding="utf-8")
        if delay_s:
            time.sleep(delay_s)
        return text

    try:
        total = int(_body(page_text(1)).get("totalCount") or 0)
        pages = max(1, math.ceil(total / page_size))
        for page in range(2, pages + 1):
            page_text(page)
            if page % 50 == 0:
                log(f"{page}/{pages}쪽")
    finally:
        if own_client:
            client.close()

    files = sorted(pages_dir.glob("page-*.json"))
    item_count = sum(len(_items(_body(f.read_text(encoding="utf-8")))) for f in files)
    manifest = {
        "source": SOURCE,
        "url": URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "page_size": page_size,
        "total_count": total,
        "pages": len(files),
        "items": item_count,
        "calls_this_run": calls,
        "complete": item_count == total,
        "files": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return {k: v for k, v in manifest.items() if k != "files"}


KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 +9


def kst_today(now: datetime | None = None) -> date:
    """받은 날 = 한국 날짜. 컨테이너 시계(UTC)의 날짜를 쓰면 00~09시에 받은 자료가 전날 폴더로 간다(2026-11-20 첫 수집)."""
    return (now or datetime.now(timezone.utc)).astimezone(KST).date()


def default_out_dir(data_dir: Path, today: date | None = None) -> Path:
    return data_dir / "raw" / "kea_building_rating" / (today or kst_today()).isoformat()


def service_key() -> str:
    return os.getenv("DATA_GO_KR_SERVICE_KEY", "")
