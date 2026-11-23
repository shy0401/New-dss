# 전국 수집 순위 표 (`backend/reference/region_priority.csv`)

`build_region_priority.py`가 지역마다 단계(1 덜 끝난 수집 · 2 더운 지역 또는 제주 · 3 공동주택 지역난방 30% 이상 · 4 나머지)를 매기고, 단계 안에서는 K-apt 단지가 많은 순으로 순위를 낸다. 만든 날 READY인 지역은 뺀다. 규칙 · 결과: [지역 우선순위 기록](../../docs/records/2026-11-21-region-priority.md). 2026-11-24에 PC 실험 폴더에서 옮겼다.

```
python build_region_priority.py <regions.txt> backend/reference/regional_climate_guide.csv backend/reference/apartment_energy_stats_2025.csv <out.csv>
```

- `regions.txt`: 한 줄에 `지역 코드|K-apt 단지 수|지역 상태`(DB `national_complexes`의 지역별 단지 수와 `study_regions.status`, 상태가 없으면 빈칸). 11-21에 쓴 파일은 남아 있지 않다
- 확인(2026-11-24): 지금 표에서 거꾸로 만든 입력(단계 1 = `PARTIAL`, 나머지 빈칸)으로 돌리면 저장소 표와 **바이트까지 같음**. 스크립트 · 참고표 두 개로 같은 표가 나온다는 뜻이고, 11-21의 DB 상태를 다시 만든 것은 아니다. 지금 DB로 다시 만들면 그 뒤 READY가 된 지역이 빠져 표가 달라진다
