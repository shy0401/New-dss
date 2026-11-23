-- B2 1안: 2015~2025년 평균 도일(지역 코드별). 12개월이 다 있는 해만 연 합계로 셈. 전주는 weather_monthly(지역 코드 52110으로 표기)
with m as (
  select region_code, use_ym, source_type, provider, hdd, cdd from region_weather_monthly
  union all
  select '52110', use_ym, source_type, provider, hdd, cdd from weather_monthly
), y as (
  select region_code, left(use_ym,4) yr, count(*) filter (where hdd is not null) n_hdd, sum(hdd) hdd, sum(cdd) cdd,
         count(*) filter (where source_type = 'FALLBACK') n_fallback, string_agg(distinct provider, '+') providers
  from m where use_ym between '201501' and '202512' group by 1,2
)
select region_code, count(*) filter (where n_hdd=12) years_complete, round(avg(hdd) filter (where n_hdd=12)::numeric,0) hdd_normal,
       round(avg(cdd) filter (where n_hdd=12)::numeric,0) cdd_normal,
       round(min(hdd) filter (where n_hdd=12)::numeric,0) hdd_min, round(max(hdd) filter (where n_hdd=12)::numeric,0) hdd_max,
       sum(n_fallback) months_fallback, string_agg(distinct providers, '+') providers
from y group by 1 order by 1;
