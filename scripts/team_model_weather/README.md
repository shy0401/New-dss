# 팀 변화 모델의 기상 (`deploy/team-model/station_annual.csv`)

팀 학습 표가 다른 도시의 ASOS를 쓰던 지역(파주 · 의정부 · 고양 → 서울, 세종 → 대전 등)에, 그 지역 **같은 시의 한 지점**을 모든 해에 쓰게 하는 표를 만든다. 규칙은 2026-11-17에 정했다(기준 문서 5.8, [팀 데이터셋](../../docs/TEAM_DATASET.md)). 2026-11-24에 PC 실험 폴더에서 옮겼고, 남아 있던 중간 결과로 다시 골라 **지금 표의 62행이 모두 같게** 나옴을 확인했다(원본에서는 성남 · 화성 두 지역이 나중에 끝에 붙어 줄 순서만 다름, [기록](../../docs/records/2026-11-24-pc-tools-to-repo.md)).

| 파일 | 하는 일 |
|---|---|
| `aws_annual_for_team.py` | 기상청 API허브 방재기상월보(`AwsMtlyInfoService`): 지점일람표 · 일자료 → 지점 · 해별 연 평균기온 · HDD18 · CDD24 후보. 키 `KMA_APIHUB_KEY`(`.env`). 원본은 `data/raw/kma/aws_apihub/`에 그대로 두고 다시 돌리면 원본을 읽음 |
| `asos_annual_for_team.py` | 공공데이터포털 ASOS 일자료 → 같은 연 값(api 컨테이너 안에서, 키 · 캐시 사용). 원본 `data/raw/kma/asos_team/<지점>/` |
| `region_stations.csv` | 지역 → 같은 시 후보 지점(ASOS · AWS). 2026-11-17 기록의 표와 지점일람표 주소 · 좌표로 정한 것(안산 545는 일람표 주소가 평택이나 좌표로 안산) |
| `select_station_annual.py` | 팀 해(2014 · 2016 · 2018 · 2019 · 2021 · 2022 · 2024) 중 완전한 해가 가장 많은 지점 하나(같으면 ASOS)를 고르고, 그 지점의 완전한 해만 씀. 완전한 팀 해가 없는 지역(평택 · 양주)은 행 없음 = 서비스에서 NULL(다른 도시로 대체하지 않음) |

## 다시 만드는 차례
1. `python aws_annual_for_team.py <저장소> stations 201401,201606,201906,202206,202412 data/ops/aws_stations.csv`
2. `python aws_annual_for_team.py <저장소> daily <지점,...> 2014 2025 data/ops/aws_annual_candidates.csv`
3. api 컨테이너에서: `python /tools/asos_annual_for_team.py 41480=99,36110=239 2014 2025 /data/ops/asos_team.csv`(이 폴더를 `/tools`로 붙임)
4. `python select_station_annual.py data/ops/aws_annual_candidates.csv data/ops/asos_team.csv deploy/team-model/station_annual.csv`
- 기상 규칙은 팀 규칙과 같음: 하루라도 빠진 달은 값 없음, 12달이 다 있어야 그해 값, 연 평균은 날수 가중, 월보의 `)` 표시값은 쓰고 `x`는 결측
- READY 중 팀 표가 없는 새 지역의 같은 규칙 표(U2-c 준비, `data/derived/u2c_weather/station_annual_new_regions.csv`)는 아직 서비스 표에 넣지 않았다
