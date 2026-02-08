"""
Live Simulation - Updates equipment every 15 seconds
EXACT LOGIC FROM USER - NO MODIFICATIONS
"""
import asyncio
import random
from datetime import datetime
from typing import Dict


async def simulate_live_sensors(plant_data, predictor, ws_manager, db, high_t, med_t):
    """
    Background task - updates sensors every 15 seconds
    Updates equipment readings, recalculates predictions, updates sensor history
    """
    print("🔄 Live simulation started")
    
    while True:
        try:
            current_time = datetime.now()
            
            for equip in plant_data["equipment"]:
                # 1. Update cumulative hours
                equip["readings"]["operating_hours"] += 0.0042 
                
                # 2. Add realistic jitter to readings
                for key in equip["readings"]:
                    if isinstance(equip["readings"][key], (int, float)) and key not in ["heats_count"]:
                        equip["readings"][key] += random.uniform(-0.5, 0.5)

                # 3. CRITICAL: Recalculate ML Prediction
                new_prob = predictor.predict(equip["readings"])
                equip["failure_probability"] = new_prob
                equip["health_score"] = int((1 - new_prob) * 100)
                
                # Update risk category
                if new_prob > high_t:
                    equip["risk_category"] = "high"
                    equip["status"] = "red"
                elif new_prob > med_t:
                    equip["risk_category"] = "medium"
                    equip["status"] = "yellow"
                else:
                    equip["risk_category"] = "low"
                    equip["status"] = "green"

                # 4. Update Time-Series History for UI Charts
                for s_id, s_data in plant_data["sensors"].items():
                    if s_data["equipment_id"] == equip["equip_id"]:
                        # Extract the key name from the ID
                        r_key = s_id.replace(f"{equip['equip_id']}-", "").lower().replace("-", "_")
                        
                        # Handle specific mapping cases
                        if r_key == "health_score": 
                            val = equip["health_score"]
                        elif r_key == "clogging_index": 
                            val = equip["readings"].get("clogging_index")
                        else: 
                            val = equip["readings"].get(r_key)

                        if val is not None:
                            s_data["history"].append({
                                "timestamp": current_time.isoformat(), 
                                "value": float(val)
                            })
                            if len(s_data["history"]) > 100: 
                                s_data["history"].pop(0)
                            s_data["current_value"] = float(val)

            # Broadcast update to WebSocket clients
            high_count = len([e for e in plant_data["equipment"] if e["risk_category"] == "high"])
            await ws_manager.broadcast({
                "type": "plant_update", 
                "timestamp": current_time.isoformat(),
                "high_risk_count": high_count,
                "total_equipment": len(plant_data["equipment"])
            })
            
            print(f"⚡ Update: {current_time.strftime('%H:%M:%S')} - High risk: {high_count}")
            
        except Exception as e:
            print(f"❌ Simulation Error: {e}")
            import traceback
            traceback.print_exc()
        
        await asyncio.sleep(15)
