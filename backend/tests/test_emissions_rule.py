
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain import carbon_kg
from app.emissions import GAS_CO2EQ_KG_PER_TJ, GAS_FACTOR, GAS_FACTOR_ID, GAS_NCV_FACTOR, OLD_GAS_FACTOR_IDS, ensure_gas_factor
from app.models import EmissionFactor


def test_city_gas_factor_values():
    # GIR 2021 승인 도시가스(LNG) CO2 15.236 tC/TJ × 44/12 = 55,865.3 + IPCC 2006 상업·주거 CH4 5×28 + N2O 0.1×265 = 56,031.8 kgCO2eq/TJ
    assert GAS_CO2EQ_KG_PER_TJ == 56031.8
    # 1 kWh = 3.6e-6 TJ (순발열량 기준 kWh)
    assert GAS_NCV_FACTOR == 0.20171
    # 건축HUB kWh(총발열량 기준)에 맞춤: × 38.5/42.7 (에너지열량환산기준 도시가스 순/총발열량)
    assert GAS_FACTOR == 0.1819
    assert round(GAS_NCV_FACTOR / GAS_FACTOR - 1, 3) == 0.109


def test_gas_factor_is_registered_as_national_factor_and_replaces_the_old_rule():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[EmissionFactor.__table__])
    db = sessionmaker(engine)()
    db.add(EmissionFactor(id=OLD_GAS_FACTOR_IDS[0], energy_type="GAS", factor=0.1826, factor_unit="kgCO2eq/kWh", reference_year=2006,
                          source="old rule", source_url="", effective_from="2000-01-01", notes="가정"))
    db.commit()
    ensure_gas_factor(db)
    ensure_gas_factor(db)  # idempotent
    rows = db.query(EmissionFactor).all()
    assert len(rows) == 1 and rows[0].id == GAS_FACTOR_ID and not rows[0].id.startswith("rule-")
    assert "15.236" in rows[0].notes and "가정" not in rows[0].notes
    factor = {"factor": rows[0].factor, "factor_unit": rows[0].factor_unit}
    assert round(carbon_kg(1000.0, factor), 1) == 181.9
