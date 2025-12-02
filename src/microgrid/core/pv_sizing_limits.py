
import pandas as pd

def compute_pv_sizing_limits(consumption_csv, pv_table_csv, selected_module, safety_margin_percent=10):
    # Load consumption and irradiance data
    df = pd.read_csv(consumption_csv)
    
    # Load PV table
    pv_table = pd.read_csv(pv_table_csv)
    
    # Match selected module efficiency from the table
    if 'PV_types' not in pv_table.columns or 'STC_eff' not in pv_table.columns:
        raise ValueError("Base_PV_table must include 'PV_types' and 'STC_eff' columns.")
    
    module_row = pv_table[pv_table['PV_types'] == selected_module]
    if module_row.empty:
        raise ValueError(f"Selected module '{selected_module}' not found in PV table.")
    
    module_efficiency = module_row.iloc[0]['STC_eff']
    
    # Step 1: Calculate total annual consumption
    total_annual_kwh = df['consumption'].sum()

    # Step 2: Determine 115% production limit
    max_production_kwh = 1.15 * total_annual_kwh
    # This will be refined after yield is calculated

    # Step 3: Estimate yield based on insolation and module efficiency
    df['kWh_per_kW'] = (df['insolation'] * module_efficiency) / 1000
    specific_yield = df['kWh_per_kW'].sum()

    # Step 4: Compute system size from 115% rule
    max_system_kw_by_production = max_production_kwh / specific_yield

    # Step 5: Estimate service capacity from peak demand + margin
    peak_kw = df['consumption'].max()
    estimated_service_capacity_kw = peak_kw * (1 + safety_margin_percent / 100)
    max_system_kw_by_service = 0.90 * estimated_service_capacity_kw

    # Step 6: Final limit and reason
    final_allowed_system_kw = min(max_system_kw_by_production, max_system_kw_by_service)
    limiting_factor = "production limit (115%)" if final_allowed_system_kw == max_system_kw_by_production else "service capacity (90%)"

    return {
        "Selected PV Module": selected_module,
        "Module Efficiency": module_efficiency,
        "Annual Consumption (kWh)": total_annual_kwh,
        "Peak Hourly Demand (kW)": peak_kw,
        "Estimated Service Capacity (kW)": estimated_service_capacity_kw,
        "Specific Yield (kWh/kW/year)": specific_yield,
        "115% Production Cap (kWh)": max_production_kwh,
        "Max Size by Production (kW)": max_system_kw_by_production,
        "Max Size by Service Capacity (kW)": max_system_kw_by_service,
        "Final Allowed System Size (kW)": final_allowed_system_kw,
        "Limiting Factor": limiting_factor
    }

# Example usage
if __name__ == "__main__":
    consumption_file = "yearly_consumption.csv"
    pv_table_file = "Base_PV_table.csv"
    selected_module_name = "Mono Si PERC"
    
    results = compute_pv_sizing_limits(consumption_file, pv_table_file, selected_module_name)
    for k, v in results.items():
        print(f"{k}: {v:.2f}" if isinstance(v, float) else f"{k}: {v}")
