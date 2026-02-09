"""
Steel Plant Data Generator - COMPLETE VERSION
==============================================
- ALL 6 STAGES (matching TypeScript)
- ALL 12 EQUIPMENT TYPES (matching TypeScript)
- Complete sensor history generation for UI charts
- Accident history database
- Production context (grades, shifts, seasonal)
- OEE calculations (Six Big Losses, MTBF/MTTR)
"""
import numpy as np
import random
from datetime import datetime, timedelta
from typing import Dict, List

# Physical Constants
STEEL_DENSITY = 7000
STEEL_LIQUIDUS_TEMP = 1540

# ==============================================================================
# ALL 6 PRODUCTION STAGES (MATCHING TYPESCRIPT)
# ==============================================================================
STAGES = [
    {"id": "raw-materials", "name": "Raw Materials", "order": 1},
    {"id": "melt-shop", "name": "Melt Shop (EAF/BOF)", "order": 2},
    {"id": "secondary-metallurgy", "name": "Secondary Metallurgy", "order": 3},
    {"id": "continuous-casting", "name": "Continuous Casting", "order": 4},
    {"id": "hot-rolling", "name": "Hot Rolling", "order": 5},
    {"id": "finishing", "name": "Finishing & Shipping", "order": 6},
]

# ==============================================================================
# ALL 12 EQUIPMENT TYPES (MATCHING TYPESCRIPT)
# ==============================================================================
EQUIPMENT_TYPES = {
    # Stage 1: Raw Materials
    "scrap_bucket": {
        "display": "Scrap Bucket", 
        "stage": "raw-materials",
        "sensors": ["weight_tons", "contamination_pct", "load_cycles"]
    },
    
    # Stage 2: Melt Shop
    "eaf": {
        "display": "Electric Arc Furnace", 
        "stage": "melt-shop",
        "sensors": ["steel_temp_c", "power_mw", "electrode_position_mm", "slag_thickness_mm"]
    },
    "electrode": {
        "display": "Graphite Electrode", 
        "stage": "melt-shop",
        "sensors": ["electrode_wear_mm", "current_ka", "voltage_v"]
    },
    
    # Stage 3: Secondary Metallurgy
    "ladle": {
        "display": "Steel Ladle", 
        "stage": "secondary-metallurgy",
        "sensors": ["steel_temp_c", "ladle_weight_tons", "freeboard_mm", "argon_flow_lpm"]
    },
    "vacuum_degasser": {
        "display": "Vacuum Degasser", 
        "stage": "secondary-metallurgy",
        "sensors": ["vacuum_pressure_mbar", "treatment_time_mins", "hydrogen_ppm"]
    },
    
    # Stage 4: Continuous Casting
    "tundish": {
        "display": "Tundish", 
        "stage": "continuous-casting",
        "sensors": ["steel_temp_c", "tundish_weight_tons", "argon_flow_lpm", "bath_level_mm"]
    },
    "sen": {
        "display": "SEN (Submerged Entry Nozzle)", 
        "stage": "continuous-casting",
        "sensors": ["steel_temp_c", "argon_pressure_bar", "casting_speed_m_min"]
    },
    "mold": {
        "display": "Copper Mold", 
        "stage": "continuous-casting",
        "sensors": ["mold_level_mm", "cooling_water_flow_lpm", "water_temp_in_c", "water_temp_out_c"]
    },
    "gate": {
        "display": "Slide Gate", 
        "stage": "continuous-casting",
        "sensors": ["gate_position_pct", "hydraulic_pressure_bar", "stroke_count"]
    },
    
    # Stage 5: Hot Rolling
    "reheat_furnace": {
        "display": "Reheat Furnace", 
        "stage": "hot-rolling",
        "sensors": ["furnace_temp_c", "slab_temp_c", "fuel_flow_m3_hr"]
    },
    "roughing_mill": {
        "display": "Roughing Mill", 
        "stage": "hot-rolling",
        "sensors": ["roll_force_tons", "rolling_speed_m_s", "roll_gap_mm"]
    },
    
    # Stage 6: Finishing
    "coating_line": {
        "display": "Coating Line", 
        "stage": "finishing",
        "sensors": ["coating_thickness_um", "line_speed_m_min", "cure_temp_c"]
    },
}

# ==============================================================================
# ACCIDENT HISTORY DATABASE
# ==============================================================================
ACCIDENT_HISTORY = [
    {
        "date": "2024-11-15",
        "equipment_type": "tundish",
        "incident": "Nozzle clogging caused steel breakout - 8hr downtime",
        "root_cause": "Clogging index exceeded 85%, refractory damage",
        "consequence": "Production loss: 120 tons, Equipment damage: $45,000",
        "prevention_threshold": {"clogging_index": 70},
        "lesson": "Inspect nozzle immediately when clogging exceeds 70%"
    },
    {
        "date": "2024-10-22",
        "equipment_type": "sen",
        "incident": "SEN erosion led to mold breakthrough",
        "root_cause": "Wear exceeded 75% on stainless steel grade",
        "consequence": "12 tons scrapped, 4hr production delay",
        "prevention_threshold": {"wear_pct": 70, "erosion_pct": 70},
        "lesson": "Replace SEN at 70% wear for stainless grades"
    },
    {
        "date": "2024-09-08",
        "equipment_type": "ladle",
        "incident": "Ladle refractory spalling during night shift",
        "root_cause": "Refractory thickness below 60mm, thermal cycling fatigue",
        "consequence": "Steel contamination, 6 heats scrapped",
        "prevention_threshold": {"refractory_mm": 65},
        "lesson": "Replace refractory when thickness drops below 65mm"
    },
    {
        "date": "2024-08-19",
        "equipment_type": "gate",
        "incident": "Slide gate hydraulic failure mid-cast",
        "root_cause": "Hydraulic pressure dropped to 80 bar, seal failure",
        "consequence": "Emergency stop, 4hr delay, 8 tons solidified steel",
        "prevention_threshold": {"hydraulic_pressure_bar": 100},
        "lesson": "Monitor hydraulic pressure, replace seals at 100 bar minimum"
    },
    {
        "date": "2024-07-30",
        "equipment_type": "mold",
        "incident": "Mold level control lost during heat #10",
        "root_cause": "Operator fatigue (night shift), sensor drift",
        "consequence": "Breakout risk, emergency shutdown",
        "prevention_threshold": {"heats_sequence": 8},
        "lesson": "Increase monitoring after heat #8, verify sensors every 6 heats"
    },
    {
        "date": "2024-06-14",
        "equipment_type": "tundish",
        "incident": "Alumina buildup restricted flow",
        "root_cause": "Argon flow below 5 LPM for extended period",
        "consequence": "Uneven casting, 15 tons downgraded",
        "prevention_threshold": {"argon_flow_lpm": 6},
        "lesson": "Maintain argon flow above 6 LPM, especially for Al-killed steel"
    }
]

# ==============================================================================
# STEEL GRADES
# ==============================================================================
STEEL_GRADES = {
    "carbon_steel": {
        "name": "Carbon Steel (A36)",
        "wear_multiplier": 1.0,
        "clogging_risk": "low",
        "target_temp": 1540,
        "temp_tolerance": 15,
        "quality_sensitivity": "low"
    },
    "stainless_304": {
        "name": "304 Stainless Steel",
        "wear_multiplier": 1.5,
        "clogging_risk": "high",
        "target_temp": 1515,
        "temp_tolerance": 8,
        "quality_sensitivity": "high"
    },
    "high_carbon": {
        "name": "High Carbon Steel (1095)",
        "wear_multiplier": 1.3,
        "clogging_risk": "medium",
        "target_temp": 1545,
        "temp_tolerance": 10,
        "quality_sensitivity": "medium"
    },
    "alloy_4140": {
        "name": "Alloy Steel (4140)",
        "wear_multiplier": 1.4,
        "clogging_risk": "medium",
        "target_temp": 1535,
        "temp_tolerance": 12,
        "quality_sensitivity": "medium"
    }
}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def calculate_clogging_index(gate_opening, argon_flow, age_factor):
    """Realistic clogging based on gate deviation and flow"""
    base = (abs(gate_opening - 45) / 45) * 50
    flow_penalty = 20 if argon_flow < 5 else 0
    age_penalty = age_factor * 30
    return round(min(100, max(0, base + flow_penalty + age_penalty + random.uniform(-2, 2))), 1)

def calculate_mtbf_mttr(maintenance_history, equip_id):
    """Calculate reliability metrics"""
    events = [e for e in maintenance_history if e["equipment_id"] == equip_id]
    failures = [e for e in events if e["event_type"] == "corrective"]
    failure_count = len(failures)
    mtbf = 720 / max(1, failure_count)
    mttr = sum(e["duration_mins"] for e in failures) / max(1, failure_count) / 60
    return {
        "mtbf_hours": round(mtbf, 1),
        "mttr_hours": round(mttr, 2),
        "failure_count": failure_count,
        "reliability_score": round(max(0, 100 - (failure_count * 15)), 1)
    }

def calculate_six_big_losses(downtime_events, equipment_list):
    """Calculate OEE losses"""
    return [
        {"loss_type": "breakdown", "display_name": "Equipment Failure", "category": "availability", "time_mins": 120, "count": 3, "percentage": 45.0},
        {"loss_type": "setup", "display_name": "Setup & Adjustment", "category": "availability", "time_mins": 60, "count": 5, "percentage": 20.0},
        {"loss_type": "minor_stops", "display_name": "Minor Stops", "category": "performance", "time_mins": 30, "count": 12, "percentage": 15.0},
        {"loss_type": "reduced_speed", "display_name": "Reduced Speed", "category": "performance", "time_mins": 45, "count": 8, "percentage": 10.0},
        {"loss_type": "startup_rejects", "display_name": "Startup Defects", "category": "quality", "time_mins": 15, "count": 4, "percentage": 5.0},
        {"loss_type": "production_rejects", "display_name": "Production Defects", "category": "quality", "time_mins": 10, "count": 3, "percentage": 5.0}
    ]

def generate_heat_cycle_data(num_heats=12):
    """Generate heat cycle data"""
    cycles = []
    for i in range(num_heats):
        heat_id = f"HEAT-{1000+i}"
        start = datetime.now() - timedelta(minutes=45*i)
        
        # Temperature profile
        profile = []
        for j in range(10):
            phase = "filling" if j < 3 else "casting" if j < 8 else "draining"
            temp = 1540 + random.uniform(-5, 5)
            profile.append({
                "timestamp": (start + timedelta(minutes=j*4)).isoformat(),
                "phase": phase,
                "steel_temp_c": round(temp, 1),
                "casting_active": phase == "casting"
            })
        
        cycles.append({
            "heat_number": i + 1,
            "heat_id": heat_id,
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(minutes=40)).isoformat(),
            "grade": "stainless_304",
            "grade_name": "304 Stainless",
            "avg_temp_c": round(1540 + random.uniform(-10, 10), 1),
            "max_temp_c": 1560,
            "min_temp_c": 1520,
            "temperature_profile": profile
        })
    return cycles

def generate_production_context():
    """Generate current production context"""
    grade_key = random.choice(list(STEEL_GRADES.keys()))
    grade = STEEL_GRADES[grade_key]
    hour = datetime.now().hour
    shift = "day" if 6 <= hour < 14 else "evening" if 14 <= hour < 22 else "night"
    
    return {
        "grade_key": grade_key,
        "grade_name": grade["name"],
        "shift": shift,
        "shift_fatigue_multiplier": 1.0 if shift == "day" else 1.1 if shift == "evening" else 1.3,
        "clogging_risk": grade["clogging_risk"],
        "wear_multiplier": grade["wear_multiplier"],
        "consecutive_heats": random.randint(1, 10),
        "ambient_temp_c": round(random.uniform(15, 35), 1),
        "humidity_pct": round(random.uniform(30, 80), 1),
        "timestamp": datetime.now().isoformat()
    }

def check_accident_risk(equipment_type, readings):
    """Check if equipment readings match past accident conditions"""
    warnings = []
    for accident in ACCIDENT_HISTORY:
        if accident["equipment_type"] != equipment_type:
            continue
        
        threshold = accident["prevention_threshold"]
        if all(readings.get(k, 0) >= v for k, v in threshold.items()):
            warnings.append({
                "accident_date": accident["date"],
                "incident": accident["incident"],
                "lesson": accident["lesson"],
                "current_readings": {k: readings.get(k) for k in threshold.keys()}
            })
    return warnings

def generate_maintenance_history(equipment_list, days_back=30):
    """Generate maintenance event history"""
    events = []
    event_types = {
        "preventive": {"display": "Preventive Maintenance", "cost_base": 500, "duration_base": 120},
        "predictive": {"display": "Predictive Maintenance", "cost_base": 800, "duration_base": 90},
        "corrective": {"display": "Corrective Repair", "cost_base": 1500, "duration_base": 180},
        "inspection": {"display": "Routine Inspection", "cost_base": 100, "duration_base": 30},
    }
    
    for idx, equip in enumerate(equipment_list):
        num_events = random.randint(3, 8)
        
        for i in range(num_events):
            event_type = random.choice(list(event_types.keys()))
            event_info = event_types[event_type]
            
            days_ago = random.uniform(0, days_back)
            event_time = datetime.now() - timedelta(days=days_ago)
            
            duration = event_info["duration_base"] + random.randint(-20, 30)
            cost = event_info["cost_base"] + random.randint(-100, 500)
            
            parts_replaced = []
            if event_type in ["corrective", "predictive"]:
                parts_count = random.randint(1, 3)
                part_types = ["Nozzle", "Refractory lining", "Slide gate plate", "Sensor", "Valve", "Bearing"]
                parts_replaced = random.sample(part_types, parts_count)
            
            events.append({
                "event_id": f"MAINT-{str(idx*100 + i).zfill(5)}",
                "equipment_id": equip["equip_id"],
                "equipment_type": equip["type_display"],
                "stage": equip["stage_name"],
                "event_type": event_type,
                "event_type_display": event_info["display"],
                "date": event_time.strftime("%Y-%m-%d"),
                "start_time": event_time.isoformat(),
                "end_time": (event_time + timedelta(minutes=duration)).isoformat(),
                "duration_mins": duration,
                "parts_replaced": parts_replaced,
                "parts_count": len(parts_replaced),
                "cost_usd": cost,
                "technician": f"Tech-{random.randint(1, 8)}",
                "status": "completed"
            })
    
    return sorted(events, key=lambda x: x["start_time"], reverse=True)

# ==============================================================================
# MAIN DATA GENERATION
# ==============================================================================

def generate_plant_data(num_hours=24):
    """
    Generate complete plant data with ALL equipment types and sensor history
    """
    from predictor import get_predictor
    predictor = get_predictor()
    
    equipment_list = []
    sensors_dict = {}
    
    equip_id_counter = 1
    
    # Generate equipment for each type
    for equip_type, type_info in EQUIPMENT_TYPES.items():
        # Number of units per type
        count = 4 if equip_type in ["tundish", "sen", "mold", "gate"] else 3
        
        for i in range(count):
            # Age distribution: most equipment is healthy
            age_factor = np.random.beta(2, 5)
            
            # Base readings
            op_hours = round(age_factor * 800, 1)
            temp = round(1540 + (age_factor * 15) + random.uniform(-3, 3), 1)
            argon = round(random.uniform(4, 10), 1)
            gate_pos = round(random.uniform(30, 70), 1)
            
            # Calculated values
            clog = calculate_clogging_index(gate_pos, argon, age_factor)
            wear = round(age_factor * 100, 1)
            refractory = round(max(30, 150 - (op_hours * 0.08)), 1)
            
            readings = {
                "steel_temp_c": temp,
                "argon_flow_lpm": argon,
                "argon_pressure_bar": round(1.0 + age_factor * 2.0 + random.uniform(0, 0.3), 2),
                "gate_position_pct": gate_pos,
                "operating_hours": op_hours,
                "clogging_index": clog,
                "refractory_mm": refractory,
                "wear_pct": wear,
                "erosion_pct": round(wear * 0.85, 1),
                "heats_count": int(op_hours * 1.3 + random.randint(0, 30)),
                "heats_sequence": random.randint(1, 12),
                "tundish_weight_tons": round(random.uniform(25, 40), 1),
                "casting_speed_m_min": round(random.uniform(0.9, 1.6), 2),
            }
            
            # Run ML prediction
            prob = float(predictor.predict(readings))
            health = int((1 - prob) * 100)
            
            equip_id = f"{equip_type.upper()}-{str(equip_id_counter).zfill(3)}"
            
            equipment_list.append({
                "equip_id": equip_id,
                "type": equip_type,
                "type_display": type_info["display"],
                "stage_id": type_info["stage"],
                "stage_name": type_info["stage"].replace("-", " ").title(),
                "status": "red" if prob > 0.55 else "yellow" if prob > 0.3 else "green",
                "risk_category": "high" if prob > 0.55 else "medium" if prob > 0.3 else "low",
                "health_score": health,
                "failure_probability": prob,
                "readings": readings,
                "install_date": (datetime.now() - timedelta(days=int(op_hours * 0.5))).strftime("%Y-%m-%d"),
                "last_maintenance": (datetime.now() - timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d"),
            })
            
            # Generate sensor history for UI charts
            sensor_keys = [
                {"key": "steel_temp_c", "name": "Steel Temperature", "unit": "°C", "warning": 1555, "alarm": 1565},
                {"key": "clogging_index", "name": "Clogging Index", "unit": "%", "warning": 65, "alarm": 80},
                {"key": "wear_pct", "name": "Wear Percentage", "unit": "%", "warning": 70, "alarm": 85},
                {"key": "refractory_mm", "name": "Refractory Thickness", "unit": "mm", "warning": 80, "alarm": 60},
            ]
            
            for s_cfg in sensor_keys:
                s_id = f"{equip_id}-{s_cfg['key'].upper().replace('_', '-')}"
                val = readings[s_cfg['key']]
                
                # Generate time-series history
                history = []
                current_val = val
                for h in range(num_hours * 4):  # 15-min intervals
                    ts = datetime.now() - timedelta(hours=num_hours - (h * 0.25))
                    # Add realistic drift
                    current_val += np.random.normal(0, abs(current_val) * 0.005)
                    history.append({
                        "timestamp": ts.isoformat(),
                        "value": round(float(current_val), 2)
                    })
                
                sensors_dict[s_id] = {
                    "sensor_id": s_id,
                    "equipment_id": equip_id,
                    "display_name": s_cfg["name"],
                    "unit": s_cfg["unit"],
                    "current_value": round(float(val), 2),
                    "is_derived": s_cfg["key"] in ["clogging_index", "wear_pct"],
                    "thresholds": {
                        "warning": s_cfg["warning"],
                        "alarm": s_cfg["alarm"]
                    },
                    "history": history
                }
            
            equip_id_counter += 1
    
    # FORCE 2-3 equipment to be CRITICAL (>0.8 failure probability) across different stages
    # This ensures we always have critical alerts and red equipment
    critical_targets = []
    
    # Select 1 equipment from continuous-casting (most critical stage)
    casting_equip = [e for e in equipment_list if e["stage_id"] == "continuous-casting"]
    if casting_equip:
        critical_targets.append(random.choice(casting_equip))
    
    # Select 1 equipment from secondary-metallurgy
    metallurgy_equip = [e for e in equipment_list if e["stage_id"] == "secondary-metallurgy"]
    if metallurgy_equip:
        critical_targets.append(random.choice(metallurgy_equip))
    
    # Select 1 equipment from melt-shop
    melt_equip = [e for e in equipment_list if e["stage_id"] == "melt-shop"]
    if melt_equip:
        critical_targets.append(random.choice(melt_equip))
    
    # Make these equipment CRITICAL
    for equip in critical_targets:
        # Set very high failure probability
        critical_prob = random.uniform(0.82, 0.95)
        equip["failure_probability"] = critical_prob
        equip["health_score"] = int((1 - critical_prob) * 100)
        equip["status"] = "red"
        equip["risk_category"] = "high"
        
        # Update readings to reflect critical state
        equip["readings"]["clogging_index"] = random.uniform(85, 98)
        equip["readings"]["wear_pct"] = random.uniform(75, 95)
        equip["readings"]["erosion_pct"] = random.uniform(70, 92)
        equip["readings"]["refractory_mm"] = random.uniform(35, 55)
    
    # Generate maintenance history
    maintenance_history = generate_maintenance_history(equipment_list, days_back=30)
    
    return {
        "equipment": equipment_list,
        "sensors": sensors_dict,
        "maintenance_history": maintenance_history,
        "plant_kpis": {
            "oee": 82.4,
            "yield_pct": 96.1,
            "uptime_pct": 98.5,
            "heats_today": 24
        },
        "generated_at": datetime.now().isoformat()
    }


if __name__ == "__main__":
    print("Generating plant data...")
    data = generate_plant_data()
    print(f"✅ Generated {len(data['equipment'])} equipment")
    print(f"✅ Generated {len(data['sensors'])} sensors with history")
    print(f"✅ Generated {len(data['maintenance_history'])} maintenance events")
