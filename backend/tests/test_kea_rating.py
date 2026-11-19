"""효율등급 인증 원본 받기: 받은 그대로 저장, 끊겨도 이어 받기, 키를 남기지 않기, 오류 쪽은 저장하지 않기."""
import json

import httpx
import pytest

from app.kea_rating import RatingFetchError, fetch_all

KEY = "test-key-123"


def _page(page: int, total: int, size: int) -> str:
    start = (page - 1) * size
    items = [{"RQID": str(i), "GRD_NAME": "1등급", "LOC_ADDR": "NULL"} for i in range(start, min(start + size, total))]
    return json.dumps({"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
                                    "body": {"pageNo": str(page), "totalCount": str(total), "numOfRows": str(size),
                                             "items": {"item": items}}}}, ensure_ascii=False)


def _client(total: int, size: int, asked: list[int]) -> httpx.Client:
    def send(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pageNo"])
        assert request.url.params["serviceKey"] == KEY and request.url.params["apiType"] == "json"
        asked.append(page)
        return httpx.Response(200, text=_page(page, total, int(request.url.params["numOfRows"])))
    return httpx.Client(transport=httpx.MockTransport(send))


def test_saves_every_page_as_received_and_counts_items(tmp_path):
    asked: list[int] = []
    result = fetch_all(tmp_path, KEY, client=_client(250, 100, asked), page_size=100, delay_s=0)
    assert asked == [1, 2, 3]
    assert result["total_count"] == 250 and result["items"] == 250 and result["pages"] == 3 and result["complete"]
    assert (tmp_path / "pages" / "page-0002.json").read_text(encoding="utf-8") == _page(2, 250, 100)
    for f in tmp_path.rglob("*.json"):
        assert KEY not in f.read_text(encoding="utf-8")


def test_a_second_run_asks_only_for_missing_pages(tmp_path):
    fetch_all(tmp_path, KEY, client=_client(250, 100, []), page_size=100, delay_s=0)
    (tmp_path / "pages" / "page-0003.json").unlink()
    asked: list[int] = []
    result = fetch_all(tmp_path, KEY, client=_client(250, 100, asked), page_size=100, delay_s=0)
    assert asked == [3] and result["complete"] and result["calls_this_run"] == 1


def test_an_error_answer_is_not_saved_as_data(tmp_path):
    def send(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=json.dumps({"response": {"header": {"resultCode": "22", "resultMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"}}}))
    with pytest.raises(RatingFetchError, match="22"):
        fetch_all(tmp_path, KEY, client=httpx.Client(transport=httpx.MockTransport(send)), delay_s=0)
    assert not list((tmp_path / "pages").glob("*.json"))


def test_needs_a_key(tmp_path):
    with pytest.raises(RatingFetchError):
        fetch_all(tmp_path, "  ", client=_client(1, 100, []), delay_s=0)
