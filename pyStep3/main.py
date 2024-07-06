import pandas as pd
import numpy as np
import copy
import os
import json

def make_input_json(region: int, ua_target: float, eta_ac_target: float, eta_ah_target: float, a_env: float, is_storage: bool, operation_mode: str):
    """_summary_

    Args:
        region (int): 地域区分
        ua_target (float): 設計住戸の目標外皮平均熱貫流率[W/(m2･K)]
        eta_ac_target (float): 設計住戸の冷房期平均日射熱取得率[－]
        eta_ah_target (float): 設計住戸の暖房期平均日射熱取得率[－]
        a_env (float): 設計住戸の外皮面積の合計[m2]
        is_storage (bool): 蓄熱の利用ありの場合True
        operation_mode (str): 'kyositu_kanketu' or 'kyositu_renzoku' or 'zenkan_renzoku'
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

    # common辞書の作成
    common = make_common(region=region)
    # building辞書の作成
    building = make_building()
    # room辞書の作成
    # 室名
    room_name = np.array(['mor', 'main_bed', 'child_1', 'child_2', 'nor', 'kaima', 'attic', 'found'])
    # 床面積
    floor_area = np.array([29.81, 13.25, 10.76, 10.77, 55.49, 52.17, 67.90, 66.05])
    # 室気積（家具熱容量を含む）
    volume = np.array([811.88, 364.04, 295.70, 295.81, 1541.20, 282.07, 699.62, 378.06])
    # スケジュール名
    schedule_name = np.array(['mor_', 'main_bed_', 'child_1_', 'child_2_', 'nor_', 'zero', 'zero', 'zero'], dtype=object) \
            + np.array([operation_mode] * 5 + [''] * 3, dtype=object)
    schedule_json = []
    for name in schedule_name:
        with open('schedule/' + name + '.json') as f:
            schedule_json.append(json.load(f))
    # 集約した部屋間の熱容量（家具の熱容量として計上）
    internal_thermal_capacity = np.array([113295.0, 0.001, 0.001, 0.001, 1237844.0, 0.001, 0.001, 0.001])
    room = [make_room(i, room_name[i], floor_area[i], volume[i], internal_thermal_capacity[i], schedule_json[i]) for i in range(len(room_name))]
    # 外壁
    connected_room_id = np.array([0, 0, 0, 3, 2, 3, 1, 1, 4, 4, 4, 4, 5, 5, 5, 5], dtype='int')
    if is_cold_region:
        area = np.array([14.07, 7.27, 3.5, 8.08, 14.76, 7.75, 4.36, 6.33, 18.97, 38.11, 2.73, 4.78, 0.25, 1.37])
    else:
        area = np.array([14.45, 9.09, 3.77, 8.39, 15.17, 7.43, 4.36, 8.77, 19.7, 39.02, 2.73, 4.78, 0.25, 1.37])
    direction = np.array(['e', 's', 'n', 'e', 's', 'w', 'e', 's', 'w', 'n', 'e', 's', 'w', 'n'])
    exterior_wall = [make_dictionary_for_exterior_wall(i, connected_room_id[i], area[i], direction[i], u_calc_wall) for i in range(len(area))]
    # 不透明な開口部
    connected_room_id = np.array([4, 4, 6], dtype='int')
    if is_cold_region:
        area = np.array([1.89, 1.35, 67.9])
    else:
        area = np.array([1.89, 1.62, 67.9])
    u_value_opaque_part = np.array([u_calc_door, u_calc_door, 4.51])
    direction = np.array(['w', 'n', 'top'])
    opaque_part = [make_dictionary_for_door(i + 16, connected_room_id[i], area[i], direction[i], u_value_opaque_part[i]) for i in range(len(area))]
    # 透明な開口部
    if is_cold_region:
        connected_room_id = np.array([4, 0, 0, 0, 0, 4, 4, 4, 4, 1, 2, 3, 3, 1, 4, 4], dtype='int')
        area = np.array([2.15, 2.97, 2.15, 2.15, 0.6, 0.35, 0.35, 0.35, 0.35, 1.82, 2.97, 2.97, 0.35, 1.31, 0.84, 0.35])
        direction = np.array(['s', 's', 's', 'e', 'e', 'n', 'n', 'w', 'n', 's', 's', 's', 'e', 'w', 'n', 'n'])
        solar_shading_d_h = np.array([1.3, 1.8, 1.3, 0, 0, 0, 0, 0, 0, 1.05, 1.95, 1.95, 0, 0, 0, 0, 0])
    else:
        connected_room_id = np.array([4, 0, 0, 0, 0, 4, 4, 4, 4, 1, 2, 3, 3, 1, 4, 4, 4], dtype='int')
        area = np.array([4.59, 3.47, 3.47, 2.15, 0.98, 0.54, 0.54, 0.54, 0.54, 1.73, 3.22, 3.22, 0.66, 0.99, 0.99, 0.54, 0.54])
        direction = np.array(['s', 's', 's', 'e', 'e', 'n', 'n', 'w', 'n', 's', 's', 's', 'e', 'w', 'n', 'n', 'w'])
        solar_shading_d_h = np.array([0.3, 0.91, 0.91, 0, 0, 0, 0, 0, 0, 0.65, 0.65, 0.65, 0, 0, 0, 0, 0])

    solar_shading_existence = np.array([True, True, True, False, False, False, False, False, False, True, True, True, False, False, False, False, False])
    solar_shading_depth = np.array([0.3, 0.91, 0.91, 0, 0, 0, 0, 0, 0, 0.65, 0.65, 0.65, 0, 0, 0, 0, 0])
    solar_shadeing_d_e = np.array([0.6, 0.48, 0.48, 0, 0, 0, 0, 0, 0, 0.45, 0.45, 0.45, 0, 0, 0, 0, 0])
    solar_shading_part = [{'existence': solar_shading_existence[i], "input_method": "simple", 'depth': solar_shading_depth[i], 'd_h': solar_shading_d_h[i], 'd_e': solar_shadeing_d_e[i]} for i in range(len(area))]
    transparent_part = [make_dictionary_for_window(i + 19, connected_room_id[i], area[i] * f_eta, direction[i], u_calc_window, eta_c_calc_window, solar_shading_part[i]) for i in range(len(area))]

    # 内壁の作成
    # 2階床
    part_id = np.array([52, 60, 66], dtype='int')
    rear_part_id = np.array([53, 61, 67], dtype='int')
    connected_room_id = np.array([1, 2, 3], dtype='int')
    rear_connected_room_id = np.array([5, 5, 5], dtype='int')
    area = np.array([13.25, 10.76, 10.77])
    second_floor = [d for i in range(len(area)) for d in make_dictionary_2nd_floor(part_id[i], connected_room_id[i], rear_connected_room_id[i], area[i], rear_part_id[i], is_storage)]

    # 外壁
    part_id = np.array([40, 70, 78, 80], dtype='int')
    rear_part_id = np.array([41, 71, 79, 81], dtype='int')
    connected_room_id = np.array([0, 4, 4, 6], dtype='int')
    rear_connected_room_id = np.array([6, 6, 7, 5], dtype='int')
    area = np.array([0.34, 3.21, 0.63, 4.3])
    insulated_internal_wall = [d for i in range(len(area)) for d in make_dictionary_for_insulated_internal_wall(part_id[i], connected_room_id[i], rear_connected_room_id[i], area[i], rear_part_id[i], u_calc_wall)]
    # 外壁床
    part_id = np.array([44, 76], dtype='int')
    rear_part_id = np.array([45, 77], dtype='int')
    connected_room_id = np.array([0, 4], dtype='int')
    rear_connected_room_id = np.array([7, 7], dtype='int')
    area = np.array([29.81, 35.61])
    insulated_internal_floor = [d for i in range(len(area)) for d in make_dictionary_for_skin_floor(part_id[i], connected_room_id[i], rear_connected_room_id[i], area[i], rear_part_id[i], u_calc_floor, is_storage)]
    # 階間床
    part_id = np.array([42, 72], dtype='int')
    rear_part_id = np.array([43, 73], dtype='int')
    connected_room_id = np.array([0, 5], dtype='int')
    rear_connected_room_id = np.array([5, 4], dtype='int')
    area = np.array([25.67, 38.1])
    kaima_floor = [d for i in range(len(area)) for d in make_dictionary_for_kaima_floor(part_id[i], connected_room_id[i], rear_connected_room_id[i], area[i], rear_part_id[i])]
    # 間仕切壁
    part_id = np.array([36, 46, 48, 54, 56, 62, 74], dtype='int')
    rear_part_id = np.array([37, 47, 49, 55, 57, 63, 75], dtype='int')
    connected_room_id = np.array([0, 1, 1, 2, 2, 3, 4], dtype='int')
    rear_connected_room_id = np.array([4, 2, 4, 3, 4, 4, 5], dtype='int')
    area = np.array([25.84, 8.74, 8.73, 8.74, 7.09, 7.1, 2.51])
    partition_wall = [d for i in range(len(area)) for d in make_dictionary_for_partition_wall(part_id[i], connected_room_id[i], rear_connected_room_id[i], area[i], rear_part_id[i])]
    # 天井
    part_id = np.array([38, 50, 58, 64, 68], dtype='int')
    rear_part_id = np.array([39, 51, 59, 65, 69], dtype='int')
    connected_room_id = np.array([0, 1, 2, 3, 4], dtype='int')
    rear_connected_room_id = np.array([6, 6, 6, 6, 6], dtype='int')
    area = np.array([4.14, 13.25, 10.76, 10.77, 28.99])
    ceil = [d for i in range(len(area)) for d in make_dictionary_for_skin_ceiling(part_id[i], connected_room_id[i], rear_connected_room_id[i], area[i], rear_part_id[i], u_calc_ceil)]

    # 土壌
    part_id = np.array([82, 83], dtype='int')
    connected_room_id = np.array([4, 7], dtype='int')
    area = np.array([2.48, 66.05])
    ground_part = [make_dictionary_for_ground(part_id[i], connected_room_id[i], area[i]) for i in range(len(area))]

    # 機械換気の設定
    mechanical_ventilation = make_mechanical_ventiration()

    return {
        "common": common,
        "building": building,
        "rooms": room,
        "boundaries": exterior_wall + opaque_part + transparent_part + second_floor + insulated_internal_wall + insulated_internal_floor + kaima_floor + partition_wall + ceil + ground_part,
        "mechanical_ventilations": mechanical_ventilation,
        "equipments": {
            "heating_equipments": {
            },
            "cooling_equipments": {
            }
        }
    }

def make_common(region: int) -> dict:
    """common部の辞書型を返す

    Args:
        region (int): 地域区分
    Returns:
        dict: _description_
    """

    return {
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
        ],
        "weather": {
            "method": "ees",
            "region": str(region)
        }
    }

def make_building() -> dict:
    """building部の辞書型を返す

    Returns:
        dict: _description_
    """

    return {
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
        name: str,
        floor_area: float,
        volume: float,
        heatcap_of_internal: float,
        schedule_json: dict
    ) -> dict:
    """room部の辞書型を返す

    Args:
        id (int): 部屋ID
        name (str): 部屋名
        floor_area (float): 床面積[m2]
        volume (float): 室容積[m3]
        heatcap_of_internal (float): 室内の熱容量[J/K]
        schedule_json (str): スケジュール名

    Returns:
        dict: _description_
    """

    return {
        "id": id,
        "name": name,
        "sub_name": name,
        "floor_area": floor_area,
        "volume": volume,
        "ventilation": {
            "natural": 0.0
        },
        "furniture": {
            "input_method": "specify",
            "heat_capacity": heatcap_of_internal,
            "heat_cond": heatcap_of_internal * 0.00022,
            "moisture_capacity": 0.0,
            "moisture_cond": 1.0
        },
        "schedule": schedule_json
    }

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
            "thermal_capacity": hcap_1
        },
        {
            "name": "中空層",
            "thermal_resistance": R_2,
            "thermal_capacity": hcap_2
        },
        {
            "name": "住宅用グラスウール断熱材16K相当",
            "thermal_resistance": R_3,
            "thermal_capacity": hcap_3
        },
        {
            "name": "合板12mm",
            "thermal_resistance": R_4,
            "thermal_capacity": hcap_4
        },
        {
            "name": "木片セメント板13mm",
            "thermal_resistance": R_5,
            "thermal_capacity": hcap_5
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
        "layers": dictionary,
        "solar_shading_part": {
            "existence": False
        }
    }

def make_dictionary_for_skin_ceiling(
        id: int,
        connected_room_id: int,
        rear_connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int,
        u_calc: float
        ) -> dict:
    """部位の熱貫流率から天井要素の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        rear_connected_room_id (int): 隣接する部屋ID（隣室側）
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
            "thermal_capacity": hcap_1
        },
        {
            "name": "住宅用グラスウール断熱材10K相当",
            "thermal_resistance": R_2,
            "thermal_capacity": hcap_2
        }
        ]
    
    # もし、断熱なしの結果になったらlayerを削除
    if R_2 == 0.0:
        del dictionary[1]
    
    ceil_part = {
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
        "layers": dictionary,
        "solar_shading_part": {
            "existence": False
        }
    }

    return ceil_part, \
        reverse_dictionary_for_skin_ceiling(
            connected_room_id=rear_connected_room_id,
            d=copy.deepcopy(ceil_part)
            )

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
    dictionary = d['layers']
    del d['layers']
    dictionary.reverse()
    d['layers'] = dictionary
    d['is_floor'] = True
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['h_c'] = 5.0
    d['connected_room_id'] = connected_room_id

    return d

def make_dictionary_for_skin_floor(
        id: int,
        connected_room_id: int,
        rear_connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int,
        u_calc: float,
        is_storage: bool
        ) -> dict:
    """部位の熱貫流率から床要素の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        rear_connected_room_id (int): 隣接する部屋ID（隣室側）
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
            "thermal_capacity": hcap_1
        },
        {
            "name": "合板12mm",
            "thermal_resistance": R_2,
            "thermal_capacity": hcap_2
        },
        {
            "name": "住宅用グラスウール断熱材16K相当",
            "thermal_resistance": R_3,
            "thermal_capacity": hcap_3
        }
        ]
    
    # もし、断熱なしの結果になったらlayerを削除
    if R_3 == 0.0:
        del dictionary[2]
    if R_1 == 0.0:
        del dictionary[0]
    
    floor_part = {
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
        "layers": dictionary,
        "solar_shading_part": {
            "existence": False
        }
    }

    return floor_part, \
        reverse_dictionary_for_skin_floor(
            connected_room_id=rear_connected_room_id,
            d=copy.deepcopy(floor_part)
            )

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
    dictionary = d['layers']
    del d['layers']
    dictionary.reverse()
    d['layers'] = dictionary
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
        "layers": [
            {
            "name": "コンクリート",
            "thermal_resistance": 0.075,
            "thermal_capacity": 227.5512
            }
        ],
        "solar_shading_part": {
            "existence": False
        }
    }

def make_dictionary_for_partition_wall(
        id: int,
        connected_room_id: int,
        rear_connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int
        ) -> dict:
    """間仕切壁の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        rear_connected_room_id (int): 隣接する部屋ID（隣室側）
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID

    Returns:
        dict: _description_
    """

    partition_wall = {
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
        "layers": [
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
        ],
        "solar_shading_part": {
            "existence": False
        }
    }
    reverse_partition_wall = reverse_layer_for_partition_wall(
        connected_room_id=rear_connected_room_id,
        d=copy.deepcopy(partition_wall)
    )
    return partition_wall, \
        reverse_partition_wall

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
    dictionary = d['layers']
    del d['layers']
    dictionary.reverse()
    d['layers'] = dictionary
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['connected_room_id'] = connected_room_id

    return d

def make_dictionary_for_kaima_floor(
        id: int,
        connected_room_id: int,
        rear_connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int
        ) -> dict:
    """_summary_

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        rear_connected_room_id (int): 隣接する部屋ID（隣室側）
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID

    Returns:
        dict: _description_
    """

    kaima_floor = {
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
        "layers": [
            {
                "name": "石膏ボード",
                "thermal_resistance": 0.0125 / 0.22,
                "thermal_capacity": 0.0125 * 830.0
            }
        ],
        "solar_shading_part": {
            "existence": False
        }
    }
    return kaima_floor, \
        reverse_layer_for_kaima_floor(
            connected_room_id=rear_connected_room_id,
            d=copy.deepcopy(kaima_floor)
            )

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
    dictionary = d['layers']
    del d['layers']
    dictionary.reverse()
    d['layers'] = dictionary
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['connected_room_id'] = connected_room_id

    return d

def make_dictionary_2nd_floor(
        id: int,
        connected_room_id: int,
        rear_connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int,
        is_storage: bool
        ) -> dict:
    """2階の辞書型を返す
    
    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        rear_connected_room_id (int): 隣接する部屋ID（隣室側）
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID
        is_storage (bool): 蓄熱ありの場合True
    """

    second_floor = {
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
        "layers": [
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
        ],
        "solar_shading_part": {
            "existence": False
        }
    }

    if not is_storage:
        del second_floor['layers'][0]

    return second_floor, \
        reverse_layer_for_2nd_floor(
            connected_room_id=rear_connected_room_id,
            d=copy.deepcopy(second_floor)
            )
    

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
    dictionary = d['layers']
    del d['layers']
    dictionary.reverse()
    d['layers'] = dictionary
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['connected_room_id'] = connected_room_id

    return d

def make_mechanical_ventiration() -> dict:
    """機械換気の辞書型を返す

    Returns:
        dict: _description_
    """

    return [
            { "id": 0, "root_type": "type3", "volume": 60.0, "root": [0, 4]},
            { "id": 1, "root_type": "type3", "volume": 20.0, "root": [1, 4]},
            { "id": 2, "root_type": "type3", "volume": 20.0, "root": [2, 4]},
            { "id": 3, "root_type": "type3", "volume": 20.0, "root": [3, 4]},
            { "id": 4, "root_type": "type3", "volume": 20.0, "root": [4, 1, 4]},
            { "id": 5, "root_type": "type3", "volume": 20.0, "root": [4]},
            { "id": 6, "root_type": "type3", "volume": 305.6, "root": [6]},
            { "id": 7, "root_type": "type3", "volume": 165.1, "root": [7]}
        ]

def make_dictionary_for_insulated_internal_wall(
        id: int,
        connected_room_id: int,
        rear_connected_room_id: int,
        area: float,
        rear_surface_boundary_id: int,
        u_calc: float
        ) -> dict:
    """断熱内壁の辞書型を返す

    Args:
        id (int): 部位ID
        connected_room_id (int): 隣接する部屋ID
        rear_connected_room_id (int): 隣接する部屋ID（隣室側）
        area (float): 面積[m2]
        rear_surface_boundary_id (int): 隣室側の部位ID
        u_calc (float): 熱貫流率[W/(m2･K)]

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

    # layers要素の作成
    layers = [
        {
            "name": "石膏ボード10mm",
            "thermal_resistance": R_1,
            "thermal_capacity": hcap_1
        },
        {
            "name": "中空層",
            "thermal_resistance": R_2,
            "thermal_capacity": hcap_2
        },
        {
            "name": "住宅用グラスウール断熱材16K相当",
            "thermal_resistance": R_3,
            "thermal_capacity": hcap_3
        },
        {
            "name": "合板12mm",
            "thermal_resistance": R_4,
            "thermal_capacity": hcap_4
        },
        {
            "name": "木片セメント板13mm",
            "thermal_resistance": R_5,
            "thermal_capacity": hcap_5
        }
        ]
    
    # もし、断熱なしの結果になったらlayerを削除
    if R_3 == 0.0:
        del layers[2]

    insulated_internal_wall = {
        "id": id,
        "name": "外壁",
        "sub_name": "外壁",
        "connected_room_id": connected_room_id,
        "boundary_type": "internal",
        "area": area,
        "rear_surface_boundary_id": rear_surface_boundary_id,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "h_c": 5.0,
        "layers": layers,
        "solar_shading_part": {
            "existence": False
        }
    }

    return insulated_internal_wall, \
        reverse_dictionary_for_insulated_internal_wall(
            connected_room_id=rear_connected_room_id,
            d=copy.deepcopy(insulated_internal_wall)
            )


def reverse_dictionary_for_insulated_internal_wall(
        connected_room_id: int,
        d: dict
        ) -> dict:
    """断熱内壁のdictionaryの層の順序を入れ替える（隣室側の定義用）

    Args:
        connected_room_id (int): 隣接する部屋ID
        d (dict): _description_
    """

    id = d['id']
    rear_surface_boundary_id = d['rear_surface_boundary_id']
    layers = d['layers']
    del d['layers']
    layers.reverse()
    d['layers'] = layers
    d["id"] = rear_surface_boundary_id
    d["rear_surface_boundary_id"] = id
    d['connected_room_id'] = connected_room_id

    return d

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)

        return super(NumpyEncoder, self).encode(obj)

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    region = 1
    ua_target = 0.5
    eta_ac_target = 3.0 / 100
    eta_ah_target = 4.5 / 100
    a_env = 307.51
    is_storage = False
    operation_mode = 'kyositu_kanketu'

    js = make_input_json(
        region=region,
        ua_target=ua_target,
        eta_ac_target=eta_ac_target,
        eta_ah_target=eta_ah_target,
        a_env=a_env,
        is_storage=is_storage,
        operation_mode=operation_mode
    )

    with open('input.json', 'w', encoding='utf-8') as f:
        json.dump(js, f, cls=NumpyEncoder, indent=4, ensure_ascii=False)
