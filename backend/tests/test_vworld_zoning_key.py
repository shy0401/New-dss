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


def test_feature_key_parcels_by_pnu_others_by_shape():
    from app.vworld import feature_key
    p1 = {"id": "LP_PA_CBND_BUBUN.5", "geometry": box(0, 0, 10, 10), "properties": {"pnu": "5211310100100010000"}}
    p2 = {"id": "LP_PA_CBND_BUBUN.9", "geometry": box(0, 0, 10, 10.5), "properties": {"pnu": "5211310100100010000"}}
    assert feature_key("cadastral", p1) == feature_key("cadastral", p2) == "cadastral:pnu:5211310100100010000"
    b1 = {"id": "LT_C_SPBD.1", "geometry": box(0, 0, 10, 10), "properties": {}}
    b2 = {"id": "LT_C_SPBD.1", "geometry": box(20, 0, 30, 10), "properties": {}}
    assert feature_key("buildings", b1) != feature_key("buildings", b2)
    assert feature_key("greenbelt", b1).startswith("greenbelt:sha:")
    nopnu = {"id": "x", "geometry": box(0, 0, 1, 1), "properties": {}}
    assert feature_key("cadastral", nopnu).startswith("cadastral:sha:")
