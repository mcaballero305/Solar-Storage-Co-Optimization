######################### SETS #########################
set HOURS ordered;
set OPER_HOURS := {h in HOURS: ord(h) > 1};
param H0 symbolic in HOURS := first(HOURS);
set MONTHS ordered;
set onpeak within HOURS;
set offpeak within HOURS;
set PV_types;
set BATTERY_TYPES;

#################### PARAMETERS ########################
# Environment & Demand
param L {HOURS} >= 0;            # consumption per hour
param I {HOURS} >= 0;            # insolation per hour
param Temp {HOURS};         # temperature per hour
param ref_temp:= 25;
param ref_irradiance := 1000;
param A default 1.6;             # PV area (m²)
param A_tot >=0;

param month_of {HOURS} within MONTHS;  # mapping from hour to month
param prev_h {HOURS} within HOURS;  # Previous hour mapping

# PV Parameters
param pv_cost {PV_types} >= 0;   # cost for PV type (per unit capacity)
param STC_eff {PV_types} >= 0;   # efficiency at standard test conditions (%)
param temp_coeff {PV_types};# temperature coefficient (%/°C)
param O_M {PV_types} >= 0;       # O&M cost for PV type
param kW_stc {PV_types} >= 0;    # nominal power per panel (kW)
param degradation;  # Annual degradation rate
param real_eff{h in HOURS, t in PV_types} = STC_eff[t] * (1 + temp_coeff[t]*(Temp[h] - ref_temp));
param ac_pv {PV_types} >=0;

param enforce_limit_flag binary default 1;
param BIGM_PV default 1e9;
param BIGM_A  default 1e9;

# Grid Parameters
param cost_sell;            # grid selling price
param cost_grid {HOURS} >= 0;    # grid buying price per hour
param demand_rate;          # on-peak demand rate
param max_demand_rate;      # overall demand rate
param monthly_charge;       # fixed monthly charge

# Project & LCOE Parameters
param project_life;         # project lifetime (years)
param discount_rate;        # discount rate
param CRF_pv;               # Capital Recovery Factor for PV
param sizing_limit >=0;
param itc_pv >=0;
param itc_bat>=0;

# Battery Parameters
param B_rt_eff {BATTERY_TYPES} >= 0;         # round-trip efficiency
param B_dod {BATTERY_TYPES} >= 0;            # depth of discharge
param B_cost_e {BATTERY_TYPES} >= 0;         # cost for energy capacity ($/kWh)
param B_cost_p {BATTERY_TYPES} >= 0;         # cost for power capacity ($/kW)
param B_power_rating {BATTERY_TYPES} >= 0;   # battery power rating (1/h)
param B_O_M {BATTERY_TYPES} >=0;
param E_Life {BATTERY_TYPES} >= 0;           # lifetime for energy side (years)
param P_Life {BATTERY_TYPES}>= 0;
param E_Repl_Frac {BATTERY_TYPES} >= 0;  # Energy replacement fraction
param P_Repl_Frac {BATTERY_TYPES} >= 0;  # Power replacement fraction
param ch_eff {BATTERY_TYPES} >= 0;  # Charging efficiency
param dis_eff {BATTERY_TYPES} >= 0;  # Discharging efficiency
param ac_e {BATTERY_TYPES} >= 0;             # annualized cost for energy capacity
param ac_p {BATTERY_TYPES} >= 0;             # annualized cost for power capacity
param E_P_min >= 0;
param E_P_max >= 0;

# New symbolic selection parameters – these must be declared exactly:
param selected_PV symbolic within PV_types;
param selected_Battery symbolic within BATTERY_TYPES;

#################### VARIABLES #########################
# PV Installation Variables – although defined for each type, only the selected one matters.
var N {t in PV_types} >= 0 integer;
var P_pv {t in PV_types} >= 0;
#PV Operation Variables
var PV_DC {HOURS, PV_types} >= 0;
var PV_gen {HOURS, PV_types} >= 0;
var PV_gen_L{HOURS, PV_types}>=0;
var PV_gen_G{HOURS, PV_types}>=0;

# Battery Sizing Variables (these are decision variables)
var Total_Energy >= 0;  # battery energy capacity (kWh)
var Total_Power  >= 0;  # battery power (kW)
var B_energy_capacity {BATTERY_TYPES};# battery energy capacity (kWh)

#Battery Operation Variables
var SOC {HOURS, BATTERY_TYPES} >= 0;
var P_ch {HOURS,BATTERY_TYPES} >= 0;
var P_dis {HOURS,BATTERY_TYPES} >= 0;
var P_ch_grid {HOURS,BATTERY_TYPES} >= 0;
var P_ch_pv {HOURS,BATTERY_TYPES} >= 0;
var P_dis_grid {HOURS,BATTERY_TYPES} >= 0;
var P_dis_l {HOURS,BATTERY_TYPES} >= 0;

#Grid Variables
var P_monthly_onpeak{m in MONTHS} >=0;
var P_monthly_overall{m in MONTHS} >=0;
var Grid_buy_load {HOURS} >= 0;
var Grid_buy {HOURS} >= 0;
var Grid_sell {HOURS} >= 0;

# Other Variables (for example, PV production, grid interaction, battery SOC, etc.)

#Other Variables 
var Q_overall {m in MONTHS} >= 0;
var Q_onpeak {m in MONTHS} >= 0;
param M_charge := 1e6;


#################### EMISSIONS TERMS #########################
# Grid emissions factor per unit energy at hour h (e.g., kgCO2/kWh or tCO2/MWh)
param EF_grid {HOURS} >= 0 default 0;
param offset_price >= 0 default 0;# Renewable-labeled state of charge: tracks energy in the battery that originated from PV-only charging.
var SOC_renew {HOURS, BATTERY_TYPES} >= 0;


# Portion of battery discharge to LOAD in hour h that is attributable to prior PV charging (eligible for abatement).
var B_dis_offset {HOURS, BATTERY_TYPES} >= 0;


# Portion of battery discharge to GRID in hour h that is attributable to prior PV charging (eligible for abatement on exports).
var B_dis_offset_grid {HOURS, BATTERY_TYPES} >= 0;

# Total emissions offset/abatement (scalar report variable).
var Total_Emissions_Offset >= 0;



#################### OBJECTIVE #########################
minimize Total_Cost:
    # PV Costs
  	ac_pv[selected_PV]*P_pv[selected_PV] +
    
    # Battery Costs
    Total_Energy * ac_e[selected_Battery] +
    Total_Power * ac_p[selected_Battery] +
    
    # Grid Costs
    sum {h in HOURS} (Grid_buy[h] * cost_grid[h]) -
    sum {h in HOURS} (Grid_sell[h] * cost_sell) +
    sum {m in MONTHS}(demand_rate*Q_onpeak[m] + max_demand_rate*Q_overall[m] + monthly_charge)
    - offset_price * Total_Emissions_Offset;


#################### CONSTRAINTS #########################


################## EMISSIONS ACCOUTING CONSTRAINTS#############################
# Initialize renewable SOC at the first hour to 0 for the selected battery.
subject to SOC_renew_init:
SOC_renew[first(HOURS), selected_Battery] = 0;


# Also initialize the credited PV-derived discharge at the first hour to 0.
subject to Bdis_offset_init:
B_dis_offset[first(HOURS), selected_Battery] = 0;

# Initialize the credited PV-derived discharge-to-grid at the first hour to 0.
subject to Bdis_offset_grid_init:
B_dis_offset_grid[first(HOURS), selected_Battery] = 0;

# Renewable SOC evolves by adding PV charge (with charge efficiency) and
# subtracting credited discharge to LOAD (scaled by discharge efficiency).
subject to SOC_renew_dyn { h in OPER_HOURS}:
SOC_renew[h, selected_Battery] =
SOC_renew[prev_h[h], selected_Battery]
+ ch_eff[selected_Battery] * P_ch_pv[h, selected_Battery]
-  (B_dis_offset[h, selected_Battery] + B_dis_offset_grid[h, selected_Battery]) / dis_eff[selected_Battery];

# 1) Only energy actually discharged to LOAD can be credited this hour.
subject to Offset_Discharge_Limit {h in HOURS}:
B_dis_offset[h, selected_Battery] <= P_dis_l[h, selected_Battery];

# 1b) Only energy actually discharged to GRID can be credited this hour.
subject to Offset_Discharge_Grid_Limit {h in HOURS}:
B_dis_offset_grid[h, selected_Battery] <= P_dis_grid[h, selected_Battery];

# 2) Combined credit (to load + to grid) cannot exceed renewable SOC available at start of hour.
subject to Offset_From_Renewable_SOC_first:
B_dis_offset[first(HOURS), selected_Battery] + B_dis_offset_grid[first(HOURS), selected_Battery] <=
dis_eff[selected_Battery] * SOC_renew[first(HOURS), selected_Battery];


subject to Offset_From_Renewable_SOC { h in OPER_HOURS}:
B_dis_offset[h, selected_Battery] + B_dis_offset_grid[h, selected_Battery] <=
dis_eff[selected_Battery] * SOC_renew[prev_h[h], selected_Battery];
#############################################
# Emissions Abatement Accounting (reporting)
#############################################
# Total abatement = (direct PV to load) + (PV-charged discharge to load),
# each multiplied by the hour-specific grid emissions factor.
subject to Offset_Accounting:
Total_Emissions_Offset =
sum {h in HOURS}
(PV_gen_L[h, selected_PV]
+ PV_gen_G[h, selected_PV]
+ B_dis_offset[h, selected_Battery]
+ B_dis_offset_grid[h, selected_Battery]) * EF_grid[h];



#Monthly Charge Constraints
subject to Overall_Peak{m in MONTHS, h in HOURS: month_of[h] ==m}:
	Grid_buy[h] <= Q_overall[m];

subject to Onpeak_Peak{m in MONTHS, h in onpeak: month_of[h] ==m}:
	Grid_buy[h] <= Q_onpeak[m];	


# PV Constraints


subject to Array_Rating:
    P_pv[selected_PV] = kW_stc[selected_PV] * N[selected_PV];

#subject to Net_Metering_Installation_Limit:
 #   P_pv[selected_PV] <= 8000;

subject to PV_Output {h in HOURS}:
    PV_DC[h,selected_PV] = A * N[selected_PV] * (I[h] / ref_irradiance) * real_eff[h,selected_PV];

subject to PV_Generation {h in HOURS}:
    PV_gen[h,selected_PV] = PV_DC[h,selected_PV] * 0.9;

subject to Cap_PV_size:
  P_pv[selected_PV] <= enforce_limit_flag * sizing_limit
                     + (1 - enforce_limit_flag) * BIGM_PV;

subject to Cap_PV_area:
  A * N[selected_PV] <= enforce_limit_flag * A_tot
                      + (1 - enforce_limit_flag) * BIGM_A;


# Grid Constraints

# Battery Sizing and Selection Constraints
subject to Power_vs_C_rate:
    Total_Power <= B_power_rating[selected_Battery] * B_energy_capacity[selected_Battery];
        
subject to Total_Energy_Definition:
    Total_Energy = B_energy_capacity[selected_Battery];

#E/P Ratio Calculation
subject to E_P_min_val:
	Total_Energy >=Total_Power*E_P_min;
	
#E/P Ratio Maximum	
subject to E_P_Max_val:
	Total_Energy <=Total_Power*E_P_max;    
	
# Battery Charging Constraints (indexed by hour and battery type, applied only for the selected battery)
subject to ch_lim_first:
    P_ch[first(HOURS), selected_Battery] <= Total_Energy - SOC[first(HOURS), selected_Battery];


subject to ch_lim { h in OPER_HOURS}:
    P_ch[h, selected_Battery] <= Total_Energy - SOC[prev_h[h], selected_Battery];

subject to Charge_Power_Limit {h in HOURS}:
    P_ch[h, selected_Battery] <= Total_Power;

subject to Charge_Crate_Operational {h in HOURS}:
    P_ch[h, selected_Battery] <= B_power_rating[selected_Battery] * Total_Energy;

# Battery Discharging Constraints (indexed by hour and battery type, applied only for the selected battery)
subject to dis_lim_first:
    P_dis[first(HOURS), selected_Battery] <= dis_eff[selected_Battery] * (SOC[first(HOURS), selected_Battery] - (1 - B_dod[selected_Battery]) * Total_Energy);

subject to dis_lim { h in OPER_HOURS}:
    P_dis[h, selected_Battery] <= dis_eff[selected_Battery] * (SOC[prev_h[h], selected_Battery] - (1 - B_dod[selected_Battery]) * Total_Energy);

subject to Discharge_Power_Limit {h in HOURS}:
    P_dis[h, selected_Battery] <= Total_Energy * B_power_rating[selected_Battery];

# SOC Dynamics (indexed by hour and battery type, applied only for the selected battery)
subject to SOC_Dynamics { h in OPER_HOURS}:
    SOC[h, selected_Battery] = SOC[prev_h[h], selected_Battery] + ch_eff[selected_Battery] * P_ch[h, selected_Battery] - P_dis[h, selected_Battery] / dis_eff[selected_Battery];

subject to Initial_SoC:
    SOC[first(HOURS), selected_Battery] = 0.5 * Total_Energy;

subject to SOC_Limit {h in HOURS}:
    SOC[h, selected_Battery] <= Total_Energy;

subject to SOC_Minimum {h in HOURS}:
    SOC[h, selected_Battery] >= (1 - B_dod[selected_Battery]) * Total_Energy;

subject to Cyclic_Battery:
    SOC[last(HOURS), selected_Battery] = SOC[first(HOURS), selected_Battery];
      
    
# Power Balance Constraints
subject to Gen_Balance {h in HOURS}:
    PV_gen[h,selected_PV] = PV_gen_L[h,selected_PV] + PV_gen_G[h,selected_PV] + P_ch_pv[h,selected_Battery];

subject to Discharge_balance { h in OPER_HOURS}:
    P_dis[h, selected_Battery] = P_dis_grid[h, selected_Battery] + P_dis_l[h, selected_Battery];

subject to Load_Balance { h in OPER_HOURS}:
    Grid_buy_load[h] + P_dis_l[h,selected_Battery] = L[h] - PV_gen_L[h, selected_PV];

subject to Grid_balance {h in HOURS}:
    Grid_buy[h] = P_ch_grid[h,selected_Battery] + Grid_buy_load[h];

subject to Sell_Balance { h in OPER_HOURS}:
    Grid_sell[h] = PV_gen_G[h,selected_PV] + P_dis_grid[h,selected_Battery]; 

subject to Charge_balance { h in OPER_HOURS}:
    P_ch[h,selected_Battery] = P_ch_grid[h,selected_Battery] + P_ch_pv[h,selected_Battery];

    
# Battery Limit
subject to Max_battery:
    Total_Energy <= 2000;

# Selection Constraints
subject to PV_Selection {t in PV_types: t <> selected_PV}:
    N[t] = 0;

subject to Zero_Grid_buy_load_H0: 
	Grid_buy_load[H0] = 0;
subject to Zero_Grid_buy_H0:      
	Grid_buy[H0]      = 0;
subject to Zero_Grid_sell_H0:     
	Grid_sell[H0]     = 0;
subject to Zero_P_ch_H0:       
	P_ch[H0, selected_Battery]       = 0;
subject to Zero_P_dis_H0:      
	P_dis[H0, selected_Battery]      = 0;
subject to Zero_P_ch_grid_H0:  
	P_ch_grid[H0, selected_Battery]  = 0;
subject to Zero_P_ch_pv_H0:    
	P_ch_pv[H0, selected_Battery]    = 0;
subject to Zero_P_dis_l_H0:    
	P_dis_l[H0, selected_Battery]    = 0;
subject to Zero_P_dis_grid_H0: 
	P_dis_grid[H0, selected_Battery] = 0;

