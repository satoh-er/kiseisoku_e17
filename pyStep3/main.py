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
    is_eta_c_window_upper = False
    is_eta_h_window_upper = False
    eta_c_calc_window = eta_c_calc_window_dsh
    eta_h_calc_window = eta_h_calc_window_dsh
    f_eta_c = eta_c_calc_window_dsh / 0.88
    f_eta_h = eta_h_calc_window_dsh / 0.88
    f_eta = max(f_eta_c, f_eta_h)
    u_calc_window = u_calc_window_dsh
    if f_eta > 1.0:
        is_eta_window_upper = True
        # 窓の日射熱取得率を補正する
        eta_c_calc_window = eta_c_calc_window_dsh / f_eta
        eta_h_calc_window = eta_h_calc_window_dsh / f_eta
        # 窓面積を補正する
        window_area_js = window_area_js * f_eta

        # UA_targetを担保できるように窓の熱貫流率を補正する
        u_calc_window = u_calc_window_dsh / f_eta

    # 想定するU値を再現する壁体構成の辞書型を作成する
    wall = make_layers_for_exterior_wall(u_calc=u_calc_wall)
    ceil = make_layers_for_ceiling(u_calc=u_calc_ceil)
    ceil_reverse = reverse_layers_for_ceiling(ceil)

def make_layers_for_exterior_wall(u_calc: float) -> dict:
    """部位の熱貫流率から外壁要素の辞書型を返す

    Args:
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

    # layers要素の作成
    layers = [
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
        del layers[2]

    return {
        "boundary_type": "external_general_part",
        "h_c": 2.5,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "layers": layers,
        "solar_shading_part": {
            "existence": False
        },
        "is_sun_striked_outside": True,
        "outside_emissivity": 0.9,
        "outside_heat_transfer_resistance": R_o,
        "outside_solar_absorption": 0.8,
        "temp_dif_coef": 1.0
    }

def make_layers_for_ceiling(u_calc: float) -> dict:
    """部位の熱貫流率から天井要素の辞書型を返す

    Args:
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

    # layers要素の作成
    layers = [
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
        del layers[1]
    
    return {
        "boundary_type": "internal",
        "h_c": 5.0,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "layers": layers,
        "solar_shading_part": {
            "existence": False
        },
        "outside_heat_transfer_resistance": R_o
    }

def reverse_layers_for_ceiling(d: dict):
    """天井のlayersの層の順序を入れ替える（隣室側の定義用）

    Args:
        d (dict): _description_
    """

    layers = d['layers']
    del d['layers']
    layers.reverse()
    d['layers'] = layers
    d['is_floor'] = True

    return d

def make_layers_for_floor(u_calc: float, is_storage: bool) -> dict:
    """部位の熱貫流率から床要素の辞書型を返す

    Args:
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

    # layers要素の作成
    layers = [
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
        del layers[2]
    if R_1 == 0.0:
        del layers[0]
    
    return {
        "boundary_type": "internal",
        "h_c": 0.7,
        "is_solar_absorbed_inside": True,
        "is_floor": True,
        "layers": layers,
        "solar_shading_part": {
            "existence": False
        },
        "outside_heat_transfer_resistance": R_o
    }

def reverse_layers_for_floor(d: dict):
    """床のlayersの層の順序を入れ替える（隣室側の定義用）

    Args:
        d (dict): _description_
    """

    layers = d['layers']
    del d['layers']
    layers.reverse()
    d['layers'] = layers
    d['is_floor'] = False
    d['h_c'] = 5.0

    return d

def make_property_for_window(u_calc: float, eta_calc: float) -> dict:
    """部位の熱貫流率、日射熱取得率から窓要素の辞書型を返す

    Args:
        u_calc (float): 熱貫流率[W/(m2･K)]
        eta_calc (float): 日射熱取得率[－]

    Returns:
        dict: _description_
    """

    R_i = 0.11
    R_o = 0.04

    return {
        "boundary_type": "external_transparent_part",
        "h_c": 2.5,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "is_sun_striked_outside": True,
        "outside_emissivity": 0.9,
        "outside_heat_transfer_resistance": R_o,
        "u_value": u_calc,
        "inside_heat_transfer_resistance": R_i,
        "eta_value": eta_calc,
        "incident_angle_characteristics": "multiple",
        "glass_area_ratio": 1.0,
        "temp_dif_coef": 1.0
    }

def make_property_for_door(u_calc: float) -> dict:
    """部位の熱貫流率からドア要素の辞書型を返す

    Args:
        u_calc (float): 熱貫流率[W/(m2･K)]

    Returns:
        dict: _description_
    """

    R_i = 0.11
    R_o = 0.04

    return {
        "boundary_type": "external_opaque_part",
        "h_c": 2.5,
        "is_solar_absorbed_inside": True,
        "is_floor": False,
        "solar_shading_part": {
            "existence": False
        },
        "is_sun_striked_outside": True,
        "outside_emissivity": 0.9,
        "outside_heat_transfer_resistance": R_o,
        "u_value": u_calc,
        "inside_heat_transfer_resistance": R_i,
        "outside_solar_absorption": 0.8,
        "temp_dif_coef": 1.0
    }

if __name__ == '__main__':

    region = 6
    ua_target = 0.2
    eta_ac_target = 3.0 / 100
    eta_ah_target = 4.5 / 100
    a_env = 307.51
    is_storage = False

    door = make_property_for_door(u_calc=0.2)
    print(door)

    # make_input_jason(
    #     region=region,
    #     ua_target=ua_target,
    #     eta_ac_target=eta_ac_target,
    #     eta_ah_target=eta_ah_target,
    #     a_env=a_env,
    #     is_storage=is_storage
    #     )
