import pandas as pd
import numpy as np
import copy

def make_input_jason(region: int, ua_target: float, eta_ac_target: float, eta_ah_target: float, a_env: float, is_storage: bool):
    """_summary_

    Args:
        region (int): 地域区分
        ua_target (float): 設計住戸の目標外皮平均熱貫流率[W/(m2･K)]
        eta_ac_target (float): 設計住戸の冷房期平均日射熱取得率[－]
        eta_ah_target (float): 設計住戸の暖房期平均日射熱取得率[－]
        a_env (float): 設計住戸の外皮面積の合計[m2]
        is_storage (bool): 蓄熱の利用ありの場合True
    """
    
    is_cold_region = region <= 3

    df_ac = pd.read_excel('azimuth_coefficient.xlsx')
    df_info = pd.read_excel('info_of_building_part.xlsx')

    a_env_jiritsu = df_info['部位面積（開口部面積含む）'].sum()
    a_js = df_info['部位面積（開口部面積含む）'].to_numpy()
    temp_coefficient_js = df_info['温度差係数'].to_numpy()
    door_area_js = df_info['ドア（寒冷地）' if is_cold_region else 'ドア（温暖地）'].to_numpy()
    window_area_js = df_info['窓（寒冷地）' if is_cold_region else '窓（温暖地）'].to_numpy()
    # 壁体面積の計算（全体面積から開口部面積を減じる）
    wall_area_js = a_js - door_area_js - window_area_js
    cooling_sol_correction_factor_js = df_info[str(region) + '地域冷房期取得日射補正係数'].to_numpy()
    heating_sol_correction_factor_js = df_info[str(region) + '地域暖房期取得日射補正係数'].to_numpy()
    # 部位名称
    building_part_name_js = df_info['部位名称']

    # 方位係数の取得
    direction_js = df_info['方位'].to_numpy()
    cooling_azimuthal_coefficient_js \
        = np.array([df_ac[(df_ac['期間'] == '冷房') & (df_ac['方位'] == direction)][region].values[0] for direction in direction_js])
    heating_azimuthal_coefficient_js \
        = np.array([df_ac[(df_ac['期間'] == '暖房') & (df_ac['方位'] == direction)][region].values[0] for direction in direction_js])

    # 仕様基準における外壁、天井、床、窓・ドアの熱貫流率
    if is_cold_region:
        u_spec_wall = 0.35
        u_spec_ceil = 0.17
        u_spec_floor = 0.34
        u_spec_door = 2.30
        u_spec_window = 2.30
    else:
        u_spec_wall = 0.53
        u_spec_ceil = 0.24
        u_spec_floor = 0.48
        u_spec_door = 4.70
        u_spec_window = 4.70

    # 仕様基準U値の辞書作成
    d = {
        '外壁': u_spec_wall,
        '天井': u_spec_ceil,
        '床': u_spec_floor,
        'ドア': u_spec_door,
        '窓': u_spec_window,
        '土間': 0.0
    }

    # 仕様基準の部位U値のときのq値の計算
    q_spec = np.sum(wall_area_js * temp_coefficient_js * np.vectorize(d.get)(building_part_name_js)) \
            + np.sum(window_area_js * temp_coefficient_js * d['窓']) \
            + np.sum(door_area_js * temp_coefficient_js * d['ドア'])

    # 目標とするUA値のときのq値を計算する
    q_target = ua_target * a_env

    # 仕様基準U値の補正係数fuを計算する
    f_u = q_target / q_spec

    # 各部位の熱貫流率を計算（上限値でアッパーを掛ける）
    u_calc_wall = min(f_u * d['外壁'], 2.24)
    u_calc_ceil = min(f_u * d['天井'], 4.48)
    u_calc_floor = min(f_u * d['床'], 2.32 if is_storage else 2.67)
    u_calc_door = min(f_u * d['ドア'], 6.51)
    u_calc_window_dsh = min(f_u * d['窓'], 6.51)

    # 不透明な部位の日射熱取得率の計算
    eta_d_calc_wall = 0.034 * u_calc_wall
    eta_d_calc_ceil = 0.034 * u_calc_ceil
    eta_d_calc_floor = 0.034 * u_calc_floor
    eta_d_calc_door = 0.034 * u_calc_door

    # 目標m値の計算
    m_c_target = eta_ac_target * a_env
    m_h_target = eta_ah_target * a_env

    # 不透明な部位のm値の計算
    m_c_calc_opaque = np.sum(eta_d_calc_wall * a_js * cooling_azimuthal_coefficient_js) \
                    + np.sum(eta_d_calc_ceil * a_js * cooling_azimuthal_coefficient_js) \
                    + np.sum(eta_d_calc_floor * a_js * cooling_azimuthal_coefficient_js) \
                    + np.sum(eta_d_calc_door * door_area_js * cooling_azimuthal_coefficient_js)

    m_h_calc_opaque = np.sum(eta_d_calc_wall * a_js * heating_azimuthal_coefficient_js) \
                    + np.sum(eta_d_calc_ceil * a_js * heating_azimuthal_coefficient_js) \
                    + np.sum(eta_d_calc_floor * a_js * heating_azimuthal_coefficient_js) \
                    + np.sum(eta_d_calc_door * door_area_js * heating_azimuthal_coefficient_js)
    # 透明な部位のm値の計算
    m_c_calc_window = max(m_c_target - m_c_calc_opaque, 0.0)
    m_h_calc_window = max(m_h_target - m_h_calc_opaque, 0.0)

    # 透明な部位の日射熱取得率の仮計算
    eta_c_calc_window_dsh = m_c_calc_window / np.sum(window_area_js * cooling_azimuthal_coefficient_js * cooling_sol_correction_factor_js)
    eta_h_calc_window_dsh = m_h_calc_window / np.sum(window_area_js * heating_azimuthal_coefficient_js * heating_sol_correction_factor_js)

    # 透明な部位の日射熱取得率の上限値チェック
    eta_c_calc_window = eta_c_calc_window_dsh
    eta_h_calc_window = eta_h_calc_window_dsh
    f_eta_c = eta_c_calc_window_dsh / 0.88
    f_eta_h = eta_h_calc_window_dsh / 0.88
    f_eta = max(f_eta_c, f_eta_h)
    u_calc_window = u_calc_window_dsh
    if f_eta > 1.0:
        # 窓の日射熱取得率を補正する
        eta_c_calc_window = eta_c_calc_window_dsh / f_eta
        eta_h_calc_window = eta_h_calc_window_dsh / f_eta
        # 窓面積を補正する
        window_area_js = window_area_js * f_eta

        # UA_targetを担保できるように窓の熱貫流率を補正する
        u_calc_window = u_calc_window_dsh / f_eta

    # 想定するU値を再現する壁体構成の辞書型を作成する
    wall = make_dictionary_for_exterior_wall(u_calc=u_calc_wall)
    ceil = make_dictionary_for_skin_ceiling(u_calc=u_calc_ceil)
    ceil_reverse = reverse_dictionary_for_skin_ceiling(d=ceil)
    floor = make_dictionary_for_skin_floor(u_calc=u_calc_floor, is_storage=is_storage)
    floor_reverse = reverse_dictionary_for_skin_floor(d=floor)
    window_c = make_dictionary_for_window(u_calc=u_calc_window, eta_calc=eta_c_calc_window)
    window_h = make_dictionary_for_window(u_calc=u_calc_window, eta_calc=eta_h_calc_window)
    door = make_dictionary_for_door(u_calc=u_calc_door)

def make_common() -> dict:
    """common部の辞書型を返す

    Returns:
        dict: _description_
    """

    return "common": {
        "ac_method": "air_temperature",
        "ac_config": [
            {
                "mode": 1,
                "lower": 20,
                "upper": 27
            },
            {
                "mode": 2,
                "lower": 0,
                "upper": 28
            }
        ]
    }

def make_building() -> dict:
    """building部の辞書型を返す

    Returns:
        dict: _description_
    """

    return "building": {
        "infiltration": {
            "method": "balance_residential",
            "c_value_estimate": "specify",
            "story": 2,
            "c_value": 0.0,
            "inside_pressure": "negative"
            }
        }

def make_room(
        id: int,
)

def make_dictionary_for_exterior_wall(
        id: int,
        connected_room_id: int,
        area: float,
        direction: str,
        u_calc: float
        ) -> dict:
    """

        部位の熱貫流率から外壁要素の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]
        direction (str): 方位
        u_calc (float): 部位の熱貫流率[W/(m2･K)]

    Returns:
        dict: _description_
    """
    
    R_i = 0.11
    R_o = 0.04
    # 石膏ボード10mm
    lamda_1 = 0.24
    d_1 = 0.010
    crho_1 = 830
    R_1 = d_1 / lamda_1
    hcap_1 = crho_1 * d_1
    # 中空層
    R_2 = 0.09
    hcap_2 = 0.0
    # 住宅用グラスウール断熱材16K相当
    lamda_3 = 0.045
    crho_3 = 13
    # 合板　12mm
    lamda_4 = 0.16
    d_4 = 0.012
    crho_4 = 720
    R_4 = d_4 / lamda_4
    hcap_4 = crho_4 * d_4
    # 木片セメント板　13mm
    d_5 = 0.013
    lamda_5 = 0.15
    crho_5 = 1000.0
    R_5 = d_5 / lamda_5
    hcap_5 = d_5 * crho_5

    # 断熱材の熱抵抗の計算
    R_3 = max(1.0 / u_calc - R_i - R_o - R_1 - R_2 - R_4 - R_5, 0.0)
    # 断熱材の厚さの計算
    d_3 = R_3 * lamda_3
    # 断熱材の熱容量の計算
    hcap_3 = crho_3 * d_3

    # dictionary要素の作成
    dictionary = [
        {
            "name": "石膏ボード10mm",
            "thermal_resistance": R_1,
            "heat_capacity": hcap_1
        },
        {
            "name": "中空層",
            "thermal_resistance": R_2,
            "heat_capacity": hcap_2
        },
        {
            "name": "住宅用グラスウール断熱材16K相当",
            "thermal_resistance": R_3,
            "heat_capacity": hcap_3
        },
        {
            "name": "合板12mm",
            "thermal_resistance": R_4,
            "heat_capacity": hcap_4
        },
        {
            "name": "木片セメント板13mm",
            "thermal_resistance": R_5,
            "heat_capacity": hcap_5
        }
        ]
    
    # もし、断熱なしの結果になったらlayerを削除
    if R_3 == 0.0:
        del dictionary[2]

    return {
        "id": id,
        "name": "外壁",
        "sub_name": "外壁",
        "connected_room_id": connected_room_id,
        "boundary_type": "external_general_part",
        "area": area,
        "is_sun_striked_outside": True,
        "temp_dif_coef": 1.0,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "direction": direction,
        "h_c": 2.5,
        "outside_emissivity": 0.9,
        "outside_heat_transfer_resistance": R_o,
        
        "outside_solar_absorption": 0.8,
        "dictionary": dictionary,
        "solar_shading_part": {
            "existence": False
        }
    }

def make_dictionary_for_skin_ceiling(
        id: int,
        connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int,
        u_calc: float
        ) -> dict:
    """部位の熱貫流率から天井要素の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID
        u_calc (float): 部位の熱貫流率

    Returns:
        dict: _description_
    """
    
    R_i = 0.09
    R_o = 0.09
    # 石膏ボード10mm
    lamda_1 = 0.24
    d_1 = 0.010
    crho_1 = 830
    R_1 = d_1 / lamda_1
    hcap_1 = crho_1 * d_1
    # 住宅用グラスウール断熱材10K相当
    lamda_2 = 0.05
    crho_2 = 8

    # 断熱材の熱抵抗の計算
    R_2 = max(1.0 / u_calc - R_i - R_o - R_1, 0.0)
    # 断熱材の厚さの計算
    d_2 = R_2 * lamda_2
    # 断熱材の熱容量の計算
    hcap_2 = crho_2 * d_2

    # dictionary要素の作成
    dictionary = [
        {
            "name": "石膏ボード10mm",
            "thermal_resistance": R_1,
            "heat_capacity": hcap_1
        },
        {
            "name": "住宅用グラスウール断熱材10K相当",
            "thermal_resistance": R_2,
            "heat_capacity": hcap_2
        }
        ]
    
    # もし、断熱なしの結果になったらlayerを削除
    if R_2 == 0.0:
        del dictionary[1]
    
    return {
        "id": id,
        "name": "天井",
        "sub_name": "天井",
        "connected_room_id": connected_room_id,
        "boundary_type": "internal",
        "area": area,
        "rear_surface_boundary_id": rear_surface_boundary_id,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "h_c": 5.0,
        "dictionary": dictionary
    }

def reverse_dictionary_for_skin_ceiling(
        connected_room_id: int,
        d: dict
        ) -> dict:
    """天井のdictionaryの層の順序を入れ替える（隣室側の定義用）

    Args:
        connected_room_id (int): 隣接する部屋ID
        d (dict): _description_
    """

    id = d['id']
    rear_surface_boundary_id = d['rear_surface_boundary_id']
    dictionary = d['dictionary']
    del d['dictionary']
    dictionary.reverse()
    d['dictionary'] = dictionary
    d['is_floor'] = True
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['h_c'] = 5.0
    d['connected_room_id'] = connected_room_id

    return d

def make_dictionary_for_skin_floor(
        id: int,
        connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int,
        u_calc: float,
        is_storage: bool
        ) -> dict:
    """部位の熱貫流率から床要素の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID
        u_calc (float): 部位の熱貫流率
        is_storage(bool): 蓄熱ありの場合True

    Returns:
        dict: _description_
    """
    
    R_i = 0.15
    R_o = 0.15
    # コンクリート90mm（is_storage==Trueのときのみ）
    lamda_1 = 1.6
    d_1 = 0.090 if is_storage else 0.0
    crho_1 = 2000
    R_1 = d_1 / lamda_1
    hcap_1 = crho_1 * d_1
    # 合板12mm
    lamda_2 = 0.16
    d_2 = 0.012
    crho_2 = 720
    R_2 = d_2 / lamda_2
    hcap_2 = crho_2 * d_2
    # 住宅用グラスウール断熱材16K相当
    lamda_3 = 0.045
    crho_3 = 13

    # 断熱材の熱抵抗の計算
    R_3 = max(1.0 / u_calc - R_i - R_o - R_1 - R_2, 0.0)
    # 断熱材の厚さの計算
    d_3 = R_3 * lamda_3
    # 断熱材の熱容量の計算
    hcap_3 = crho_3 * d_3

    # dictionary要素の作成
    dictionary = [
        {
            "name": "コンクリート90mm",
            "thermal_resistance": R_1,
            "heat_capacity": hcap_1
        },
        {
            "name": "合板12mm",
            "thermal_resistance": R_2,
            "heat_capacity": hcap_2
        },
        {
            "name": "住宅用グラスウール断熱材16K相当",
            "thermal_resistance": R_3,
            "heat_capacity": hcap_3
        }
        ]
    
    # もし、断熱なしの結果になったらlayerを削除
    if R_3 == 0.0:
        del dictionary[2]
    if R_1 == 0.0:
        del dictionary[0]
    
    return {
        "id": id,
        "name": "床",
        "sub_name": "床",
        "connected_room_id": connected_room_id,
        "boundary_type": "internal",
        "area": area,
        "rear_surface_boundary_id": rear_surface_boundary_id,
        "is_solar_absorbed_inside": True,
        "is_floor": True,
        "h_c": 0.7,
        "dictionary": dictionary
    }

def reverse_dictionary_for_skin_floor(
        connected_room_id: int,
        d: dict
        ) -> dict:
    """床のdictionaryの層の順序を入れ替える（隣室側の定義用）

    Args:
        connected_room_id (int): 隣接する部屋ID
        d (dict): _description_
    """

    id = d['id']
    rear_surface_boundary_id = d['rear_surface_boundary_id']
    dictionary = d['dictionary']
    del d['dictionary']
    dictionary.reverse()
    d['dictionary'] = dictionary
    d['is_floor'] = False
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['h_c'] = 0.7
    d['connected_room_id'] = connected_room_id

    return d

def make_dictionary_for_window(
        id: int,
        connected_room_id: int,
        area: float,
        direction: str,
        u_calc: float,
        eta_calc: float,
        solar_shading_part: dict
        ) -> dict:
    """部位の熱貫流率、日射熱取得率から窓要素の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]
        direction (str): 方位
        u_calc (float): 熱貫流率[W/(m2･K)]
        eta_calc (float): 日射熱取得率[－]
        solar_shading_part (dict): 日射遮蔽部位の辞書型

    Returns:
        dict: _description_
    """

    R_i = 0.11
    R_o = 0.04

    return {
        "id": id,
        "name": "窓",
        "sub_name": "窓",
        "connected_room_id": connected_room_id,
        "boundary_type": "external_transparent_part",
        "area": area,
        "is_sun_striked_outside": True,
        "temp_dif_coef": 1.0,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "direction": direction,
        "h_c": 2.5,
        "outside_emissivity": 0.9,
        "outside_heat_transfer_resistance": R_o,
        "u_value": u_calc,
        "inside_heat_transfer_resistance": R_i,
        "eta_value": eta_calc,
        "incident_angle_characteristics": "multiple",
        "glass_area_ratio": 1.0,
        "solar_shading_part": solar_shading_part
    }

def make_dictionary_for_door(
        id: int,
        connected_room_id: int,
        area: float,
        direction: str,
        u_calc: float
        ) -> dict:
    """部位の熱貫流率からドア要素の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]
        direction (str): 方位
        u_calc (float): 熱貫流率[W/(m2･K)]

    Returns:
        dict: _description_
    """

    R_i = 0.11
    R_o = 0.04

    return {
        "id": id,
        "name": "ドア",
        "sub_name": "ドア",
        "connected_room_id": connected_room_id,
        "boundary_type": "external_opaque_part",
        "area": area,
        "is_sun_striked_outside": True,
        "temp_dif_coef": 1.0,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "direction": direction,
        "h_c": 2.5,
        "outside_emissivity": 0.9,
        "outside_heat_transfer_resistance": R_o,
        "u_value": u_calc,
        "inside_heat_transfer_resistance": R_i,
        "outside_solar_absorption": 0.8,
        "solar_shading_part": {
            "existence": False
        }
    }

def make_dictionary_for_roof(
        id: int,
        connected_room_id: int,
        area: float
        ) -> dict:
    """_summary_

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]

    Returns:
        dict: _description_
    """

    R_i = 0.09
    R_o = 0.04

    return {
        "id": id,
        "name": "屋根",
        "sub_name": "屋根",
        "connected_room_id": connected_room_id,
        "boundary_type": "external_opaque_part",
        "area": area,
        "is_sun_striked_outside": True,
        "temp_dif_coef": 1.0,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "direction": "top",
        "h_c": 5.0,
        "outside_emissivity": 0.9,
        "outside_heat_transfer_resistance": R_o,
        "u_value": 4.51,
        "inside_heat_transfer_resistance": R_i,
        "outside_solar_absorption": 0.8,
        "solar_shading_part": {
            "existence": False
        }
    }

def make_dictionary_for_ground(
        id: int,
        connected_room_id: int,
        area: float
        ) -> dict:
    """土間床中央部の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]

    Returns:
        dict: _description_
    """

    return {
        "id": id,
        "name": "土間",
        "sub_name": "土間",
        "connected_room_id": connected_room_id,
        "boundary_type": "ground",
        "area": area,
        "is_solar_absorbed_inside": True,
        "is_floor": True,
        "h_c": 0.7,
        "layer": [
            {
            "name": "コンクリート",
            "thermal_resistance": 0.075,
            "thermal_capacity": 227.5512
            }
        ]
    }

def make_dictionary_for_partition_wall(
        id: int,
        connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int
        ) -> dict:
    """間仕切壁の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID

    Returns:
        dict: _description_
    """

    return {
        "id": id,
        "name": "間仕切壁",
        "sub_name": "間仕切壁",
        "connected_room_id": connected_room_id,
        "boundary_type": "internal",
        "area": area,
        "rear_surface_boundary_id": rear_surface_boundary_id,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "h_c": 5.0,
        "dictionary": [
            {
                "name": "石膏ボード",
                "thermal_resistance": 0.0125 / 0.22,
                "thermal_capacity": 830.0 * 0.0125
            },
            {
                "name": "空気層",
                "thermal_resistance": 0.07,
                "thermal_capacity": 0.0
            },
            {
                "name": "石膏ボード",
                "thermal_resistance": 0.0125 / 0.22,
                "thermal_capacity": 830.0 * 0.0125
            }
        ]
    }

def reverse_layer_for_partition_wall(
        connected_room_id: int,
        d: dict
        ) -> dict:
    """間仕切壁のdictionaryの層の順序を入れ替える（隣室側の定義用）

    Args:
        connected_room_id (int): 隣接する部屋ID
        d (dict): _description_
    """

    id = d['id']
    rear_surface_boundary_id = d['rear_surface_boundary_id']
    dictionary = d['dictionary']
    del d['dictionary']
    dictionary.reverse()
    d['dictionary'] = dictionary
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['connected_room_id'] = connected_room_id

    return d

def make_dictionary_for_kaima_floor(
        id: int,
        connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int
        ) -> dict:
    """_summary_

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID

    Returns:
        dict: _description_
    """

    return {
        "id": id,
        "name": "階間床",
        "sub_name": "階間床",
        "connected_room_id": connected_room_id,
        "boundary_type": "internal",
        "area": area,
        "rear_surface_boundary_id": rear_surface_boundary_id,
        "is_solar_absorbed_inside": True,
        "is_floor": True,
        "h_c": 5.0,
        "dictionary": [
            {
                "name": "石膏ボード",
                "thermal_resistance": 0.0125 / 0.22,
                "thermal_capacity": 0.0125 * 830.0
            }
        ]
    }

def reverse_layer_for_kaima_floor(
        connected_room_id: int,
        d: dict
        ) -> dict:
    """階間床のdictionaryの層の順序を入れ替える（隣室側の定義用）

    Args:
        connected_room_id (int): 隣接する部屋ID
        d (dict): _description_
    """

    id = d['id']
    rear_surface_boundary_id = d['rear_surface_boundary_id']
    dictionary = d['dictionary']
    del d['dictionary']
    dictionary.reverse()
    d['dictionary'] = dictionary
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['connected_room_id'] = connected_room_id

    return d

def make_dictionary_2nd_floor(
        id: int,
        connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int,
        is_storage: bool
        ) -> dict:
    """2階の辞書型を返す
    
    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID
        is_storage (bool): 蓄熱ありの場合True
    """

    return {
        "id": id,
        "name": "2階床",
        "sub_name": "2階床",
        "connected_room_id": connected_room_id,
        "boundary_type": "internal",
        "area": area,
        "rear_surface_boundary_id": rear_surface_boundary_id,
        "is_solar_absorbed_inside": True,
        "is_floor": True,
        "h_c": 0.7,
        "dictionary": [
            {
                "name": "コンクリート",
                "thermal_resistance": 0.09 / 1.6,
                "thermal_capacity": 0.09 * 2000.0
            },
            {
                "name": "合板",
                "thermal_resistance": 0.012 / 0.16,
                "thermal_capacity": 0.012 * 720.0
            }
        ]
    }

def reverse_layer_for_2nd_floor(
        connected_room_id: int,
        d: dict
        ) -> dict:
    """2階のdictionaryの層の順序を入れ替える（隣室側の定義用）

    Args:
        connected_room_id (int): 隣接する部屋ID
        d (dict): _description_
    """

    id = d['id']
    rear_surface_boundary_id = d['rear_surface_boundary_id']
    dictionary = d['dictionary']
    del d['dictionary']
    dictionary.reverse()
    d['dictionary'] = dictionary
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['connected_room_id'] = connected_room_id

    return d


if __name__ == '__main__':

    region = 6
    ua_target = 0.2
    eta_ac_target = 3.0 / 100
    eta_ah_target = 4.5 / 100
    a_env = 307.51
    is_storage = False

    # door = make_dictionary_for_door(id=0, connected_room_id=0, area=5.0, direction='s', u_calc=0.2)
    # print(door)
    # window = make_dictionary_for_window(id=0, connected_room_id=0, area=5.0, direction='s', u_calc=0.2, eta_calc=0.8, solar_shading_part={"existence": False})
    # print(window)

    # skin_ceil = make_dictionary_for_skin_ceiling(id=0, connected_room_id=0, area=5.0, rear_surface_boundary_id=1, u_calc=0.2)
    # print(skin_ceil)
    # skin_ceil_reverse = reverse_dictionary_for_skin_ceiling(d=skin_ceil)
    # print(skin_ceil_reverse)

    iwall = make_dictionary_for_partition_wall(id=0, connected_room_id=0, area=5.0, rear_surface_boundary_id=1)
    print(iwall)
    iwall_reverse = reverse_layer_for_partition_wall(connected_room_id=1, d=iwall)
    print(iwall_reverse)

    # make_input_jason(
    #     region=region,
    #     ua_target=ua_target,
    #     eta_ac_target=eta_ac_target,
    #     eta_ah_target=eta_ah_target,
    #     a_env=a_env,
    #     is_storage=is_storage
    #     )
