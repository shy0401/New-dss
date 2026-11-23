from shapely.geometry import box

from app.vworld import zoning_key


def _f(fid, geom, name):
    return {"id": fid, "geometry": geom, "properties": {"uname": name}}


def test_zoning_key_follows_the_shape_and_name_not_the_vworld_number():
    # 2026-11-23: VWorld renumbered LT_C_UQ111.<n> on an update, so a later region's zone overwrote 전주 zones
    a = _f("LT_C_UQ111.118", box(0, 0, 100, 100), "일반상업지역")
    same_shape_new_number = _f("LT_C_UQ111.1365", box(0, 0, 100, 100), "일반상업지역")
    other_shape_old_number = _f("LT_C_UQ111.118", box(500, 500, 900, 900), "자연녹지지역")
    assert zoning_key("zoning", a) == zoning_key("zoning", same_shape_new_number)
    assert zoning_key("zoning", a) != zoning_key("zoning", other_shape_old_number)
    assert zoning_key("zoning", a).startswith("zoning:sha:")


def test_zoning_key_ignores_float_noise_and_vertex_order():
    a = _f("x", box(0, 0, 100, 100), "보전녹지지역")
    b = _f("y", box(0.001, 0, 100.002, 100), "보전녹지지역")
    assert zoning_key("zoning", a) == zoning_key("zoning", b)
    assert zoning_key("zoning", a) != zoning_key("zoning_management", a)
