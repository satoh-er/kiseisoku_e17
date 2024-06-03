import pandas as pd
import numpy as np

region = 6
ua_target = 0.2
eta_ac_target = 3.0 / 100
eta_ah_target = 4.5 / 100
a_env = 307.51
is_cold_region = region <= 3

df_ac = pd.read_excel('azimuth_coefficient.xlsx')
df_info = pd.read_excel('info_of_building_part.xlsx')

a_env_jiritsu = df_info['部位面積（開口部面積含む）'].sum()
a_js = df_info['部位面積（開口部面積含む）'].to_numpy()
temp_coefficient_js = df_info['温度差係数'].to_numpy()
door_area_js = df_info['ドア（寒冷地）' if is_cold_region else 'ドア（温暖地）'].to_numpy()
window_area_js = df_info['窓（寒冷地）' if is_cold_region else '窓（温暖地）'].to_numpy()
wall_area_js = a_js - door_area_js - window_area_js
cooling_sol_correction_factor_js = df_info[str(region) + '地域冷房期取得日射補正係数'].to_numpy()
heating_sol_correction_factor_js = df_info[str(region) + '地域暖房期取得日射補正係数'].to_numpy()

direction_js = df_info['方位'].to_numpy()
cooling_azimuthal_coefficient_js \
    = np.array([df_ac[(df_ac['期間'] == '冷房') & (df_ac['方位'] == direction)][region].values[0] for direction in direction_js])
heating_azimuthal_coefficient_js \
    = np.array([df_ac[(df_ac['期間'] == '暖房') & (df_ac['方位'] == direction)][region].values[0] for direction in direction_js])

print(cooling_azimuthal_coefficient_js)
print(heating_azimuthal_coefficient_js)
