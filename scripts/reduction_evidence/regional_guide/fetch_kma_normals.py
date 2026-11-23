"""기상청 기후평년값 1991~2020 일별 평년값(전 지점)을 기후표 화면의 조회(tableAjax.do)로 날짜마다 받는다.

받은 응답은 고치지 않고 날짜별 JSON 그대로 둔다. 이미 받은 날짜는 건너뛴다(끊겨도 다시 돌리면 이어 받음).
사용자 승인(2026-11-20 "추천 작업 진행해"), 기준 문서 2절에 받기 전에 등록(커밋 c5f5016).

usage: python -E -P fetch_kma_normals.py <out dir: Carbon-Urban-DSS/data/raw/kma_normals/<받은 날>>
"""
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

URL = "https://data.kma.go.kr/normals/tableAjax.do"
POINT_URL = "https://data.kma.go.kr/resources/normals/pdf_data/normals_point.xlsx"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
out = Path(sys.argv[1])
(out / "daily").mkdir(parents=True, exist_ok=True)


def post(month: int, day: int) -> bytes:
    form = {"selectElmType": "2", "selectElmCount": "99", "selectStnType": "2", "selectStnCount": "99", "difStnCount": "1",
            "schElmId": "", "txtElmNm": "", "txtUnit": "", "schStnId": "", "stnIdArr": "", "txtStnNm": "",
            "stnFileNm": "Average30Years4.json", "DEPTH1": "TBL_KOR_1991_30", "DEPTH2": "DD",
            "startMonth": str(month), "startDay": str(day), "startYear": "2021", "startWeek": "1",
            "startTdom": "DB005001", "startSesn": "DB004001"}
    req = urllib.request.Request(URL, data=urllib.parse.urlencode(form).encode(), method="POST",
                                 headers={"User-Agent": UA, "Referer": "https://data.kma.go.kr/normals/table.do",
                                          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


point = out / "normals_point.xlsx"
if not point.exists():
    req = urllib.request.Request(POINT_URL, headers={"User-Agent": UA, "Referer": "https://data.kma.go.kr/normals/info1.do"})
    with urllib.request.urlopen(req, timeout=60) as r:
        point.write_bytes(r.read())

got, bad = 0, []
for m, n in enumerate(DAYS, start=1):
    for d in range(1, n + 1):
        f = out / "daily" / f"{m:02d}-{d:02d}.json"
        if f.exists():
            continue
        body = None
        for attempt in range(4):   # 연결 시간 초과(2026-11-20 첫 시도, 43번째 날 뒤)면 쉬었다 다시
            try:
                body = post(m, d)
                break
            except OSError:
                time.sleep(10 * (attempt + 1))
        if body is None:
            bad.append((m, d, "timeout"))
            continue
        try:
            data = json.loads(body)
        except ValueError:
            bad.append((m, d, "not json"))
            continue
        if data.get("code") != "00" or not data.get("dataList"):
            bad.append((m, d, data.get("code")))
            continue
        f.write_bytes(body)
        got += 1
        time.sleep(0.3)

KST = timezone(timedelta(hours=9))
files = sorted((out / "daily").glob("*.json")) + [point]
lines = ["source: 기상청 기상자료개방포털 기후평년값(1991~2020) 일별 평년값 · 전 지점 (기후표 조회 tableAjax.do, DEPTH1=TBL_KOR_1991_30, DEPTH2=DD), 제공지점 일람표 normals_point.xlsx",
         f"url: {URL} (POST, 날짜마다) · {POINT_URL}",
         f"received: {datetime.now(KST):%Y-%m-%d %H:%M} KST (python urllib, 사용자 승인 2026-11-20). 응답을 고치지 않음",
         f"days: {len(files) - 1} 날짜 파일, 이번에 받은 것 {got}, 받지 못한 날 {bad}",
         "bytes sha256 file"]
lines += [f"{p.stat().st_size} {hashlib.sha256(p.read_bytes()).hexdigest()} {p.relative_to(out).as_posix()}" for p in files]
(out / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("got", got, "files", len(files), "bad", bad)
