with c as (select distinct on (kapt_code) kapt_code, bjd_code, gross_floor_area_m2 a, households h, management_area_m2 ma from apartment_complexes order by kapt_code, snapshot_month desc),
y as (
  select m.complex_code, sum(m.electricity_quantity) kwh
  from apartment_energy_monthly m
  where m.year_month between '202501' and '202512' and m.quality_status='SUCCESS' and m.electricity_quantity is not null
  group by 1 having count(*)=12
)
select left(c.bjd_code,5) sgg, count(*) n,
  round((percentile_cont(0.5) within group (order by y.kwh/c.a))::numeric,1) med_kwh_m2,
  round((percentile_cont(0.5) within group (order by c.a/nullif(c.h,0)))::numeric,1) med_area_per_hh,
  round(max(c.a/nullif(c.h,0))::numeric) max_area_per_hh, round(min(c.a/nullif(c.h,0))::numeric,1) min_area_per_hh,
  count(*) filter (where c.a/nullif(c.h,0) > 400) n_over400, count(*) filter (where c.a/nullif(c.h,0) < 30) n_under30
from y join c on c.kapt_code=y.complex_code where c.a>0
group by 1 order by 1;
