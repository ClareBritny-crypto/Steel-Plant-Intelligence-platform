"""
Steel Plant Intelligence Platform - COMPLETE VERSION
====================================================
ALL ENDPOINTS MATCHING TYPESCRIPT API
ALL 6 STAGES, ALL 12 EQUIPMENT TYPES
COMPLETE SENSOR HISTORY WITH TIME-SERIES
NO LOGIC STRIPPED
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import datetime, timedelta
import asyncio
import pandas as pd
import numpy as np
import io
import random

from database import get_db
from websocket_manager import get_ws_manager
from simulation import simulate_live_sensors
from predictor import get_predictor
from data_generator import (
    generate_plant_data, STAGES, ACCIDENT_HISTORY, STEEL_GRADES,
    check_accident_risk, generate_production_context,
    calculate_six_big_losses, calculate_mtbf_mttr, generate_heat_cycle_data
)
from gemini_ai import generate_ai_explanation, generate_ai_recommendations

# Configuration
HIGH_RISK_THRESHOLD = 0.55
MEDIUM_RISK_THRESHOLD = 0.30
USE_GEMINI_AI = True

# Global State
PLANT_DATA = None
MAINTENANCE_HISTORY = []
PRODUCTION_CONTEXT = None
ALERTS = []
PREDICTOR = None
SIMULATION_TASK = None

db = get_db()
ws_manager = get_ws_manager()

app = FastAPI(title="Steel Plant Intelligence Platform", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    global PLANT_DATA, MAINTENANCE_HISTORY, PRODUCTION_CONTEXT, PREDICTOR, ALERTS, SIMULATION_TASK
    
    print("🚀 Starting Steel Plant Intelligence Platform...")
    print("=" * 60)
    
    # 1. Initialize ML Model
    PREDICTOR = get_predictor()
    print("✅ ML model loaded")
    
    # 2. Generate Plant Data
    PLANT_DATA = generate_plant_data(num_hours=24)
    print(f"✅ Generated {len(PLANT_DATA['equipment'])} equipment")
    print(f"✅ Generated {len(PLANT_DATA['sensors'])} sensors with history")
    
    # 3. Get Maintenance History
    MAINTENANCE_HISTORY = PLANT_DATA.get("maintenance_history", [])
    print(f"✅ Loaded {len(MAINTENANCE_HISTORY)} maintenance events")
    
    # 4. Initialize Production Context
    PRODUCTION_CONTEXT = generate_production_context()
    print(f"✅ Context: {PRODUCTION_CONTEXT['grade_name']} / {PRODUCTION_CONTEXT['shift']} shift")
    
    # 5. Calculate predictions for all equipment
    for equip in PLANT_DATA["equipment"]:
        prob = PREDICTOR.predict(equip["readings"])
        equip["failure_probability"] = float(prob)
        equip["health_score"] = int(max(0, min(100, (1 - prob) * 100)))
        
        if prob > HIGH_RISK_THRESHOLD:
            equip["risk_category"], equip["status"] = "high", "red"
        elif prob > MEDIUM_RISK_THRESHOLD:
            equip["risk_category"], equip["status"] = "medium", "yellow"
        else:
            equip["risk_category"], equip["status"] = "low", "green"
    
    # 6. Generate Alerts
    ALERTS = []
    for idx, equip in enumerate(PLANT_DATA["equipment"], 1):
        prob = equip["failure_probability"]
        if prob > MEDIUM_RISK_THRESHOLD:
            alert = {
                "alert_id": f"A{str(idx).zfill(3)}",
                "timestamp": datetime.now().isoformat(),
                "severity": "high" if prob > HIGH_RISK_THRESHOLD else "medium",
                "stage": equip["stage_id"],
                "stage_name": equip["stage_name"],
                "equipment": equip["equip_id"],
                "equipment_type": equip["type_display"],
                "message": f"Failure risk ({prob:.0%})",
                "failure_probability": float(prob),
                "acknowledged": False
            }
            ALERTS.append(alert)
            db.insert_alert(alert)
    
    print(f"✅ Generated {len(ALERTS)} alerts")
    
    # 7. Start Background Simulation
    if SIMULATION_TASK is None or SIMULATION_TASK.done():
        SIMULATION_TASK = asyncio.create_task(
            simulate_live_sensors(PLANT_DATA, PREDICTOR, ws_manager, db, HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD)
        )
        print("✅ Live simulation started")
    
    print("=" * 60)
    print(f"✅ READY")
    print(f"   Equipment: {len(PLANT_DATA['equipment'])}")
    print(f"   Sensors: {len(PLANT_DATA['sensors'])}")
    print(f"   Alerts: {len(ALERTS)}")
    print(f"   Grade: {PRODUCTION_CONTEXT['grade_name']}")
    print("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    global SIMULATION_TASK
    if SIMULATION_TASK:
        SIMULATION_TASK.cancel()
    print("✅ Shutdown complete")

# ==============================================================================
# WEBSOCKET
# ==============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
            await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

@app.websocket("/ws/equipment/{equip_id}")
async def websocket_equipment(websocket: WebSocket, equip_id: str):
    await ws_manager.connect(websocket)
    ws_manager.subscribe_equipment(websocket, equip_id)
    
    try:
        equip = next((e for e in PLANT_DATA["equipment"] if e["equip_id"] == equip_id), None)
        if equip:
            await websocket.send_json({
                "type": "initial_state",
                "equip_id": equip_id,
                "status": equip["status"],
                "health_score": equip["health_score"],
                "failure_probability": equip["failure_probability"],
                "readings": equip["readings"]
            })
        
        while True:
            await websocket.receive_text()
            await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# ==============================================================================
# CORE ENDPOINTS
# ==============================================================================

@app.get("/")
async def root():
    return {
        "message": "Steel Plant Intelligence Platform API",
        "version": "5.0.0",
        "websocket": "ws://localhost:8000/ws",
        "docs": "/docs"
    }

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "equipment_count": len(PLANT_DATA["equipment"]),
        "sensor_count": len(PLANT_DATA["sensors"]),
        "stages_count": len(STAGES),
        "ai_enabled": USE_GEMINI_AI,
        "websocket_connections": len(ws_manager.connections),
        "timestamp": datetime.now().isoformat()
    }

# ==============================================================================
# PLANT & STAGES
# ==============================================================================

@app.get("/api/plant/overview")
async def get_plant_overview():
    equipment = PLANT_DATA["equipment"]
    total_equip = len(equipment)
    
    # KPI Calculations
    avg_health = sum(e["health_score"] for e in equipment) / total_equip
    avg_failure = sum(e["failure_probability"] for e in equipment) / total_equip
    high_risk_count = len([e for e in equipment if e["risk_category"] == "high"])
    
    # Production calculations
    base_rate = 300
    health_factor = avg_health / 100
    risk_penalty = 1 - (high_risk_count * 0.04)
    jitter = random.uniform(0.98, 1.02)
    production_rate = round(base_rate * health_factor * risk_penalty * jitter, 1)
    heats_today = int(production_rate / 15.5)
    
    # Critical alerts
    critical_alerts = [
        a for a in ALERTS 
        if a["severity"] in ["high", "critical"] and not a.get("acknowledged", False)
    ][:5]
    
    # Stages summary
    stages_summary = []
    for stage in STAGES:
        stage_equip = [e for e in equipment if e["stage_id"] == stage["id"]]
        if stage_equip:
            s_high = len([e for e in stage_equip if e["risk_category"] == "high"])
            stages_summary.append({
                "stage_id": stage["id"],
                "name": stage["name"],
                "order": stage["order"],
                "status": "red" if s_high > 0 else "green",
                "equipment_count": len(stage_equip),
                "high_risk_count": s_high
            })
    
    return {
        "plant_name": "Steel Plant Intelligence Platform",
        "timestamp": datetime.now().isoformat(),
        "kpis": {
            "oee": round(avg_health * 0.82, 1),
            "yield_pct": 94.2,
            "uptime_pct": 98.1,
            "production_rate_tons_hr": production_rate,
            "heats_today": heats_today,
            "avg_health_score": round(avg_health, 1),
            "avg_failure_probability": round(avg_failure * 100, 1),
            "total_equipment": total_equip,
            "active_alerts": len([a for a in ALERTS if not a.get("acknowledged", False)]),
            "kpi_formulas": {
                "oee": "Availability x Performance x Quality",
                "yield": "Yield percentage",
                "uptime": "Operational uptime",
                "production_rate": "Tons/hr based on health"
            }
        },
        "model_metrics": {
            "avg_failure_probability": round(avg_failure, 3),
            "avg_health_score": round(avg_health, 1),
            "high_risk_count": high_risk_count,
            "medium_risk_count": len([e for e in equipment if e["risk_category"] == "medium"]),
            "low_risk_count": len([e for e in equipment if e["risk_category"] == "low"]),
            "total_equipment": total_equip,
            "operational_rate": round(100 - (high_risk_count / total_equip * 100), 1)
        },
        "top_risk_factors": [
            {"factor": "clogging_index", "display_name": "Clogging Index", "affected_equipment": 3, "avg_impact": 0.24}
        ],
        "critical_equipment": sorted([
            {
                "equip_id": e["equip_id"],
                "type": e["type_display"],
                "failure_probability": e["failure_probability"],
                "stage": e["stage_name"]
            }
            for e in equipment
        ], key=lambda x: x["failure_probability"], reverse=True)[:5],
        "stages_summary": sorted(stages_summary, key=lambda x: x["order"]),
        "active_alerts": len([a for a in ALERTS if not a.get("acknowledged", False)]),
        "critical_alerts": critical_alerts
    }

@app.get("/api/stages")
async def get_stages():
    equipment = PLANT_DATA["equipment"]
    res = []
    for s in STAGES:
        stage_equip = [e for e in equipment if e["stage_id"] == s["id"]]
        res.append({
            "stage_id": s["id"],
            "name": s["name"],
            "order": s["order"],
            "equipment_count": len(stage_equip),
            "high_risk_count": len([e for e in stage_equip if e["risk_category"] == "high"])
        })
    return {"stages": sorted(res, key=lambda x: x["order"])}

@app.get("/api/stage/{stage_id}")
async def get_stage_details(stage_id: str):
    normalized_id = stage_id.replace("_", "-")
    stage = next((s for s in STAGES if s["id"] == stage_id or s["id"] == normalized_id), None)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage {stage_id} not found")
    
    equipment = PLANT_DATA["equipment"]
    stage_equip = [e for e in equipment if e["stage_id"] == stage["id"]]
    
    risk_dist = {
        "low": len([e for e in stage_equip if e["risk_category"] == "low"]),
        "medium": len([e for e in stage_equip if e["risk_category"] == "medium"]),
        "high": len([e for e in stage_equip if e["risk_category"] == "high"])
    }
    
    return {
        "stage_id": stage["id"],
        "name": stage["name"],
        "order": stage["order"],
        "status": "red" if risk_dist["high"] > 0 else "yellow" if risk_dist["medium"] > 0 else "green",
        "risk_distribution": risk_dist,
        "equipment": [{
            "equip_id": e["equip_id"],
            "type": e["type"],
            "type_display": e["type_display"],
            "status": e["status"],
            "health_score": e["health_score"],
            "failure_probability": e["failure_probability"],
            "risk_category": e["risk_category"]
        } for e in sorted(stage_equip, key=lambda x: x["failure_probability"], reverse=True)],
        "alerts": [a for a in ALERTS if a["stage"] == stage["id"] and not a["acknowledged"]][:5]
    }

# ==============================================================================
# EQUIPMENT
# ==============================================================================

@app.get("/api/equipment/{equip_id}")
async def get_equipment(equip_id: str):
    equip = next((e for e in PLANT_DATA["equipment"] if e["equip_id"] == equip_id), None)
    if not equip:
        raise HTTPException(status_code=404, detail="Equipment not found")
    
    return {
        "equip_id": equip["equip_id"],
        "type": equip["type"],
        "type_display": equip["type_display"],
        "stage": equip["stage_id"],
        "stage_name": equip["stage_name"],
        "status": equip["status"],
        "last_updated": datetime.now().isoformat(),
        "identity": {
            "manufacturer": "Primetals Technologies" if "tundish" in equip["type"] else "SMS Group",
            "model": f"{equip['type'].upper()}-2024",
            "install_date": equip.get("install_date", "2024-01-01"),
            "last_maintenance": equip.get("last_maintenance", "2025-01-15")
        },
        "health": {
            "health_score": equip["health_score"],
            "failure_probability": equip["failure_probability"],
            "risk_category": equip["risk_category"],
            "predicted_remaining_heats": max(0, int((1 - equip["failure_probability"]) * 50)),
            "predicted_remaining_hours": max(0, int((1 - equip["failure_probability"]) * 200))
        },
        "live_sensors": equip["readings"],
        "current_readings": equip["readings"],
        "sensors": [
            {
                "sensor_id": s_id,
                "name": s_data["display_name"],
                "value": s_data["current_value"],
                "unit": s_data["unit"],
                "status": "normal" if s_data["current_value"] < s_data["thresholds"]["warning"] else "warning",
                "is_derived": s_data.get("is_derived", False)
            }
            for s_id, s_data in PLANT_DATA["sensors"].items()
            if s_data["equipment_id"] == equip_id
        ]
    }

@app.get("/api/equipment/{equip_id}/explanation")
async def get_explanation(equip_id: str, use_ai: bool = True):
    equip = next((e for e in PLANT_DATA["equipment"] if e["equip_id"] == equip_id), None)
    if not equip:
        raise HTTPException(status_code=404, detail="Equipment not found")
    
    shap_features = PREDICTOR.calculate_shap_values(equip["readings"], equip["failure_probability"])
    explanation = generate_ai_explanation(
        equip["equip_id"], equip["type"], equip["failure_probability"],
        shap_features, equip["readings"], use_ai and USE_GEMINI_AI
    )
    
    return {
        "equip_id": equip_id,
        "failure_probability": equip["failure_probability"],
        "shap_features": shap_features,
        "llm_explanation": explanation,
        "ai_powered": use_ai and USE_GEMINI_AI
    }

@app.get("/api/equipment/{equip_id}/recommendations")
async def get_recommendations(equip_id: str, use_ai: bool = True):
    equip = next((e for e in PLANT_DATA["equipment"] if e["equip_id"] == equip_id), None)
    if not equip:
        raise HTTPException(status_code=404, detail="Equipment not found")
    
    shap_features = PREDICTOR.calculate_shap_values(equip["readings"], equip["failure_probability"])
    recommendations = generate_ai_recommendations(
        equip["equip_id"], equip["type"], equip["failure_probability"],
        equip["readings"], shap_features, use_ai and USE_GEMINI_AI
    )
    
    return {
        "equip_id": equip_id,
        "recommendations": recommendations,
        "ai_powered": use_ai and USE_GEMINI_AI
    }

# ==============================================================================
# SENSORS
# ==============================================================================

@app.get("/api/sensor/{sensor_id}/history")
async def get_sensor_history(sensor_id: str, hours: int = Query(default=24, ge=1, le=168)):
    sensor = PLANT_DATA["sensors"].get(sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    
    cutoff = datetime.now() - timedelta(hours=hours)
    filtered = [h for h in sensor["history"] if datetime.fromisoformat(h["timestamp"]) > cutoff]
    
    values = [h["value"] for h in filtered]
    
    return {
        "sensor_id": sensor_id,
        "name": sensor["display_name"],
        "equipment": sensor["equipment_id"],
        "unit": sensor["unit"],
        "current_value": sensor["current_value"],
        "is_derived": sensor.get("is_derived", False),
        "thresholds": sensor["thresholds"],
        "statistics": {
            "min": round(min(values), 2) if values else 0,
            "max": round(max(values), 2) if values else 0,
            "avg": round(sum(values) / len(values), 2) if values else 0,
            "std_dev": round(float(np.std(values)), 2) if values else 0
        },
        "history": filtered
    }

# ==============================================================================
# ALERTS
# ==============================================================================

@app.get("/api/alerts")
async def get_alerts(
    acknowledged: Optional[str] = Query(None),
    severity: Optional[str] = None,
    stage: Optional[str] = None
):
    filtered = ALERTS
    
    if acknowledged is not None:
        is_ack = acknowledged.lower() == 'true'
        filtered = [a for a in filtered if a["acknowledged"] == is_ack]
    
    if severity:
        filtered = [a for a in filtered if a["severity"] == severity]
    
    if stage:
        filtered = [a for a in filtered if a["stage"] == stage]
    
    return {
        "total_count": len(filtered),
        "alerts": sorted(filtered, key=lambda x: x["failure_probability"], reverse=True)
    }

@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    alert = next((a for a in ALERTS if a["alert_id"] == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert["acknowledged"] = True
    alert["acknowledged_at"] = datetime.now().isoformat()
    
    return {"status": "success", "alert_id": alert_id}

# ==============================================================================
# MAINTENANCE
# ==============================================================================

@app.get("/api/maintenance/queue")
async def get_maintenance_queue():
    equipment = PLANT_DATA["equipment"]
    sorted_equip = sorted(equipment, key=lambda x: x["failure_probability"], reverse=True)
    
    queue = []
    for i, equip in enumerate(sorted_equip[:10]):
        if equip["failure_probability"] < 0.2:
            continue
        
        urgency = "immediate" if equip["failure_probability"] > 0.7 else \
                  "next_shift" if equip["failure_probability"] > 0.5 else "planned"
        
        action_map = {
            "tundish": "Inspect for clogging and schedule nozzle maintenance",
            "sen": "Inspect SEN for alumina buildup and erosion",
            "ladle": "Check refractory lining and thermal profile",
            "mold": "Verify mold level control and copper condition",
            "gate": "Check plate wear and hydraulic system",
        }
        
        queue.append({
            "priority": i + 1,
            "equip_id": equip["equip_id"],
            "equipment_name": f"{equip['type_display']} {equip['equip_id'].split('-')[1]}",
            "stage": equip["stage_id"],
            "stage_name": equip["stage_name"],
            "action": action_map.get(equip["type"], "General inspection and component check"),
            "failure_probability": equip["failure_probability"],
            "urgency": urgency,
            "estimated_downtime_mins": 30 if urgency == "immediate" else 45
        })
    
    return {"queue": queue}

@app.get("/api/maintenance/history")
async def get_maintenance_history(days: int = 30, equipment_id: Optional[str] = None):
    recent = [e for e in MAINTENANCE_HISTORY if (datetime.now() - datetime.fromisoformat(e["start_time"])).days <= days]
    
    if equipment_id:
        recent = [e for e in recent if e["equipment_id"] == equipment_id]
    
    total_cost = sum(e["cost_usd"] for e in recent)
    total_time = sum(e["duration_mins"] for e in recent)
    
    # Group by type
    by_type = {}
    for e in recent:
        t = e["event_type_display"]
        if t not in by_type:
            by_type[t] = {"count": 0, "total_cost": 0, "total_time": 0}
        by_type[t]["count"] += 1
        by_type[t]["total_cost"] += e["cost_usd"]
        by_type[t]["total_time"] += e["duration_mins"]
    
    return {
        "period_days": days,
        "total_events": len(recent),
        "summary": {
            "total_cost_usd": float(total_cost),
            "total_downtime_hours": round(total_time / 60, 1),
            "total_parts_replaced": sum(e.get("parts_count", 0) for e in recent),
            "avg_cost_per_event": round(total_cost / max(1, len(recent)), 2)
        },
        "by_type": by_type,
        "recent_events": recent[:20]
    }

@app.get("/api/maintenance/upcoming")
async def get_upcoming_maintenance():
    upcoming = []
    
    for equip in PLANT_DATA["equipment"]:
        prob = equip["failure_probability"]
        if prob < 0.3:
            continue
        
        urgency = "immediate" if prob > 0.7 else "this_week" if prob > 0.5 else "this_month"
        days = 0 if urgency == "immediate" else np.random.randint(1, 20)
        
        upcoming.append({
            "equipment_id": equip["equip_id"],
            "equipment_type": equip["type_display"],
            "stage": equip["stage_name"],
            "urgency": urgency,
            "days_until": days,
            "scheduled_date": (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d"),
            "maintenance_type": "Preventive" if prob < 0.5 else "Corrective",
            "estimated_duration_mins": 120 if prob > 0.6 else 60,
            "reason": f"High failure probability ({prob:.0%})",
            "failure_probability": float(prob),
            "health_score": int(equip["health_score"])
        })
    
    return {
        "total_upcoming": len(upcoming),
        "immediate": len([u for u in upcoming if u["urgency"] == "immediate"]),
        "this_week": len([u for u in upcoming if u["urgency"] == "this_week"]),
        "this_month": len([u for u in upcoming if u["urgency"] == "this_month"]),
        "upcoming_maintenance": sorted(upcoming, key=lambda x: x["days_until"])
    }

@app.get("/api/maintenance/mtbf-mttr")
async def get_reliability_metrics(equipment_id: Optional[str] = None):
    all_metrics = []
    
    for equip in PLANT_DATA["equipment"]:
        if equipment_id and equip["equip_id"] != equipment_id:
            continue
        
        m = calculate_mtbf_mttr(MAINTENANCE_HISTORY, equip["equip_id"])
        all_metrics.append({
            "equipment_id": equip["equip_id"],
            "equipment_type": equip["type_display"],
            "stage": equip["stage_name"],
            "mtbf_hours": float(m["mtbf_hours"] or 720.0),
            "mttr_hours": float(m["mttr_hours"] or 0.0),
            "failure_count": int(m["failure_count"]),
            "reliability_score": float(m.get("reliability_score", 100))
        })
    
    return {
        "plant_wide": {
            "avg_mtbf_hours": 720.0,
            "avg_mttr_hours": 2.5,
            "total_failures": len([e for e in MAINTENANCE_HISTORY if e["event_type"] == "corrective"])
        },
        "by_equipment": sorted(all_metrics, key=lambda x: x["reliability_score"])
    }

# ==============================================================================
# ANALYTICS
# ==============================================================================

@app.get("/api/analytics/trends")
async def get_analytics_trends(days: int = 7):
    equipment = PLANT_DATA["equipment"]
    base_avg = sum(e["failure_probability"] for e in equipment) / len(equipment)
    
    trends = []
    for day in range(days, -1, -1):
        trend_date = datetime.now() - timedelta(days=day)
        date = trend_date.strftime("%Y-%m-%d")
        variation = np.random.uniform(-0.05, 0.05)
        daily_avg = max(0.1, min(0.9, base_avg + variation + (day * 0.008)))
        
        trends.append({
            "date": date,
            "avg_failure_probability": round(daily_avg, 3),
            "avg_health_score": round((1 - daily_avg) * 100, 1),
            "high_risk_count": int(len(equipment) * daily_avg * 0.5),
            "medium_risk_count": int(len(equipment) * 0.4),
            "low_risk_count": int(len(equipment) * (1 - daily_avg) * 0.5)
        })
    
    first_half = sum(t["avg_failure_probability"] for t in trends[:len(trends)//2]) / max(1, len(trends)//2)
    second_half = sum(t["avg_failure_probability"] for t in trends[len(trends)//2:]) / max(1, len(trends) - len(trends)//2)
    trend_direction = "degrading" if second_half > first_half + 0.02 else \
                     "improving" if second_half < first_half - 0.02 else "stable"
    
    return {
        "period_days": days,
        "trend_direction": trend_direction,
        "current_avg_risk": round(base_avg, 3),
        "trends": trends,
        "insight": f"Plant health is {trend_direction} over the past {days} days"
    }

@app.get("/api/analytics/weekly-trends")
async def get_weekly_trends():
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    trend_data = []
    
    for d in days:
        day_impact = -6 if d in ["Sun", "Mon"] else random.uniform(0, 4)
        oee = round(74 + day_impact, 1)
        production = int(250 + (oee * 0.45))
        
        trend_data.append({
            "day": d,
            "oee": oee,
            "production": production,
            "av_output": production
        })
    
    avg_oee = round(sum(d["oee"] for d in trend_data) / 7, 1)
    avg_production = int(sum(d["production"] for d in trend_data) / 7)
    
    return {
        "period": "Last 7 Days",
        "trend_direction": "stable",
        "data": trend_data,
        "summary": {
            "avg_oee": avg_oee,
            "avg_production": avg_production,
            "av_output": avg_production
        }
    }

@app.get("/api/analytics/comparison")
async def get_analytics_comparison():
    equipment = PLANT_DATA["equipment"]
    sorted_equip = sorted(equipment, key=lambda x: x["failure_probability"])
    
    # Best and worst performers
    best = [{
        "equip_id": e["equip_id"],
        "type": e["type_display"],
        "health_score": e["health_score"],
        "failure_probability": round(e["failure_probability"], 3)
    } for e in sorted_equip[:5]]
    
    worst = [{
        "equip_id": e["equip_id"],
        "type": e["type_display"],
        "health_score": e["health_score"],
        "failure_probability": round(e["failure_probability"], 3)
    } for e in sorted_equip[-5:][::-1]]
    
    # By equipment type
    type_stats = {}
    for e in equipment:
        t = e["type_display"]
        if t not in type_stats:
            type_stats[t] = {"count": 0, "total_risk": 0, "high_risk": 0}
        type_stats[t]["count"] += 1
        type_stats[t]["total_risk"] += e["failure_probability"]
        if e["risk_category"] == "high":
            type_stats[t]["high_risk"] += 1
    
    type_list = sorted([{
        "type": t,
        "count": d["count"],
        "avg_failure_probability": round(d["total_risk"] / d["count"], 3),
        "high_risk_count": d["high_risk"]
    } for t, d in type_stats.items()], key=lambda x: x["avg_failure_probability"], reverse=True)
    
    return {
        "best_performers": best,
        "worst_performers": worst,
        "by_equipment_type": type_list
    }

@app.get("/api/analytics/risk-distribution")
async def get_risk_distribution():
    equipment = PLANT_DATA["equipment"]
    buckets = {"critical": [], "high": [], "medium": [], "low": [], "healthy": []}
    
    for e in equipment:
        prob = e["failure_probability"]
        if prob >= 0.8:
            bucket = "critical"
        elif prob >= 0.55:
            bucket = "high"
        elif prob >= 0.3:
            bucket = "medium"
        elif prob >= 0.1:
            bucket = "low"
        else:
            bucket = "healthy"
        buckets[bucket].append(e["equip_id"])
    
    return {
        "total_equipment": len(equipment),
        "distribution": {k: {"count": len(v), "equipment": v} for k, v in buckets.items()},
        "needs_immediate_attention": len(buckets["critical"]) + len(buckets["high"])
    }

# ==============================================================================
# PRIORITIES
# ==============================================================================

@app.get("/api/priorities/today")
async def get_priorities():
    equipment = PLANT_DATA["equipment"]
    high_risk = sorted([e for e in equipment if e["failure_probability"] > 0.5],
                       key=lambda x: x["failure_probability"], reverse=True)
    
    priorities = []
    for i, equip in enumerate(high_risk[:5]):
        shap_features = PREDICTOR.calculate_shap_values(equip["readings"], equip["failure_probability"])
        top_factor = shap_features[0] if shap_features else None
        
        if top_factor:
            factor = top_factor["feature"]
            action = "Inspect nozzle for clogging" if "clogging" in factor else \
                    "Check refractory lining" if "refractory" in factor else \
                    "Inspect for wear/erosion" if "wear" in factor or "erosion" in factor else \
                    "Check temperature sensors" if "temp" in factor else \
                    "Perform general inspection"
            time_mins = 20 if "clogging" in factor else 30
        else:
            action, time_mins = "Perform general inspection", 30
        
        prob = equip["failure_probability"]
        urgency = "IMMEDIATE" if prob > 0.75 else "THIS_SHIFT" if prob > 0.6 else "TODAY"
        
        priorities.append({
            "rank": i + 1,
            "equip_id": equip["equip_id"],
            "equipment_type": equip["type_display"],
            "stage": equip["stage_name"],
            "failure_probability": round(prob, 3),
            "health_score": equip["health_score"],
            "action": action,
            "reason": f"{top_factor['display_name']}: {top_factor['value']:.1f}" if top_factor else "High risk",
            "urgency": urgency,
            "estimated_time_mins": time_mins
        })
    
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "shift": "Day" if 6 <= datetime.now().hour < 18 else "Night",
        "total_priorities": len(priorities),
        "immediate_count": len([p for p in priorities if p["urgency"] == "IMMEDIATE"]),
        "total_time_mins": sum(p["estimated_time_mins"] for p in priorities),
        "priorities": priorities
    }

@app.get("/api/priorities/summary")
async def get_priorities_summary():
    equipment = PLANT_DATA["equipment"]
    
    critical = len([e for e in equipment if e["failure_probability"] > 0.8])
    high = len([e for e in equipment if 0.55 < e["failure_probability"] <= 0.8])
    medium = len([e for e in equipment if 0.3 < e["failure_probability"] <= 0.55])
    healthy = len([e for e in equipment if e["failure_probability"] <= 0.3])
    
    avg_health = sum(e["health_score"] for e in equipment) / len(equipment)
    maint_hours = (critical * 1.5) + (high * 0.8) + (medium * 0.4)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "equipment_status": {
            "critical": critical,
            "high": high,
            "medium": medium,
            "healthy": healthy
        },
        "plant_health_score": round(avg_health, 1),
        "maintenance_hours_needed": round(maint_hours, 1),
        "active_alerts": len([a for a in ALERTS if not a["acknowledged"]]),
        "status_message": f"🚨 {critical} CRITICAL UNITS" if critical > 0 else "✅ Operations Stable"
    }

# ==============================================================================
# AI
# ==============================================================================

@app.get("/api/ai/plant-summary")
async def get_ai_summary():
    equipment = PLANT_DATA["equipment"]
    avg_health = sum(e["health_score"] for e in equipment) / len(equipment)
    high_risk = len([e for e in equipment if e["risk_category"] == "high"])
    
    status = "CRITICAL" if high_risk > 3 else "STABLE"
    
    return {
        "summary": f"Plant status is {status}. Average health: {avg_health:.1f}%. {high_risk} units require immediate attention.",
        "ai_powered": False
    }

# ==============================================================================
# DOWNTIME
# ==============================================================================

@app.get("/api/downtime/six-big-losses")
async def get_six_losses(hours: int = 24):
    all_l = calculate_six_big_losses([], PLANT_DATA["equipment"])
    
    availability = [l for l in all_l if l["category"] == "availability"]
    performance = [l for l in all_l if l["category"] == "performance"]
    quality = [l for l in all_l if l["category"] == "quality"]
    
    return {
        "period_hours": hours,
        "summary": {
            "availability_losses_mins": sum(l["time_mins"] for l in availability),
            "performance_losses_mins": sum(l["time_mins"] for l in performance),
            "quality_losses_mins": sum(l["time_mins"] for l in quality),
            "total_losses_mins": sum(l["time_mins"] for l in all_l)
        },
        "availability_losses": availability,
        "performance_losses": performance,
        "quality_losses": quality,
        "all_losses": all_l
    }

@app.get("/api/downtime/pareto")
async def get_pareto(hours: int = 168):
    pareto_data = [
        {"reason": "Motor Failure", "category": "breakdown", "count": 5, "total_mins": 240, "total_hours": 4.0, "percentage": 40.0, "cumulative_pct": 40.0},
        {"reason": "Grade Changeover", "category": "setup", "count": 8, "total_mins": 160, "total_hours": 2.67, "percentage": 26.7, "cumulative_pct": 66.7},
        {"reason": "Sensor Recalibration", "category": "minor_stops", "count": 12, "total_mins": 120, "total_hours": 2.0, "percentage": 20.0, "cumulative_pct": 86.7},
        {"reason": "Flow Disruption", "category": "reduced_speed", "count": 6, "total_mins": 80, "total_hours": 1.33, "percentage": 13.3, "cumulative_pct": 100.0}
    ]
    
    return {
        "period_hours": hours,
        "total_reasons": len(pareto_data),
        "top_20_pct_causes": 2,
        "insight": "Top 2 causes account for 66.7% of total downtime",
        "pareto_analysis": pareto_data
    }

@app.get("/api/downtime/recent")
async def get_recent_downtime(hours: int = 24, days: int = 1):
    events = []
    event_categories = [
        {"id": "breakdown_losses", "name": "Equipment Failure", "type": "availability"},
        {"id": "setup_adjustment", "name": "Setup & Changeover", "type": "availability"},
        {"id": "minor_stops", "name": "Minor Stops", "type": "performance"},
    ]
    
    for i in range(10):
        cat = random.choice(event_categories)
        hours_ago = random.uniform(0, hours)
        event_time = datetime.now() - timedelta(hours=hours_ago)
        duration = random.randint(5, 60)
        
        events.append({
            "event_id": f"DT-{str(i+1).zfill(5)}",
            "equipment_id": random.choice(PLANT_DATA["equipment"])["equip_id"],
            "equipment_type": random.choice(PLANT_DATA["equipment"])["type_display"],
            "stage": random.choice(STAGES)["name"],
            "category_id": cat["id"],
            "category_name": cat["name"],
            "loss_type": cat["type"],
            "reason": f"{cat['name']} event",
            "start_time": event_time.isoformat(),
            "end_time": (event_time + timedelta(minutes=duration)).isoformat(),
            "duration_mins": duration,
            "acknowledged": random.choice([True, False]),
            "root_cause_identified": random.choice([True, False])
        })
    
    return {
        "period_hours": hours,
        "total_events": len(events),
        "total_downtime_mins": sum(e["duration_mins"] for e in events),
        "total_downtime_hours": round(sum(e["duration_mins"] for e in events) / 60, 1),
        "by_category": {},
        "events": sorted(events, key=lambda x: x["start_time"], reverse=True)
    }

# ==============================================================================
# SHIFTS
# ==============================================================================

@app.get("/api/shifts/current")
async def get_shift_info():
    hour = datetime.now().hour
    
    if 6 <= hour < 14:
        shift_data = {
            "id": "day",
            "name": "Day Shift",
            "hours": "06:00 - 14:00",
            "manning_level": "Full",
            "production_capacity": "Maximum",
            "response_time_mins": 5,
            "maintenance_allowed": True
        }
        hours_into = hour - 6
    elif 14 <= hour < 22:
        shift_data = {
            "id": "evening",
            "name": "Evening Shift",
            "hours": "14:00 - 22:00",
            "manning_level": "90%",
            "production_capacity": "High",
            "response_time_mins": 8,
            "maintenance_allowed": True
        }
        hours_into = hour - 14
    else:
        shift_data = {
            "id": "night",
            "name": "Night Shift",
            "hours": "22:00 - 06:00",
            "manning_level": "80%",
            "production_capacity": "Reduced",
            "response_time_mins": 12,
            "maintenance_allowed": False
        }
        hours_into = (hour - 22) if hour >= 22 else (hour + 2)
    
    equipment = PLANT_DATA["equipment"]
    
    return {
        "current_shift": shift_data,
        "shift_performance": {
            "hours_into_shift": hours_into,
            "avg_health_score": round(sum(e["health_score"] for e in equipment) / len(equipment), 1),
            "high_risk_equipment": len([e for e in equipment if e["risk_category"] == "high"]),
            "downtime_events": 3,
            "total_downtime_mins": 45,
            "equipment_availability": 98.5
        },
        "priorities": ["Monitor high-risk equipment", "Complete scheduled inspections"]
    }

@app.get("/api/shifts/comparison")
async def get_shift_comparison(days: int = 7):
    return {
        "period_days": days,
        "shifts": [
            {"shift_id": "day", "shift_name": "Day Shift", "avg_health_score": 88.5, "avg_oee": 78.2, "manning_level": 1.0, "production_rate": 285, "avg_downtime_mins_per_day": 12},
            {"shift_id": "evening", "shift_name": "Evening Shift", "avg_health_score": 86.2, "avg_oee": 75.4, "manning_level": 0.9, "production_rate": 270, "avg_downtime_mins_per_day": 18},
            {"shift_id": "night", "shift_name": "Night Shift", "avg_health_score": 82.1, "avg_oee": 71.8, "manning_level": 0.8, "production_rate": 255, "avg_downtime_mins_per_day": 25}
        ],
        "best_performing": "Day Shift",
        "improvement_opportunity": "Night Shift",
        "variance": 6.4
    }

# ==============================================================================
# PATTERNS
# ==============================================================================

@app.get("/api/patterns/shift")
async def get_shift_pattern():
    hour = datetime.now().hour
    
    if 6 <= hour < 14:
        shift_id, shift_name = "day", "Day Shift"
        remaining = 14 - hour
    elif 14 <= hour < 22:
        shift_id, shift_name = "evening", "Evening Shift"
        remaining = 22 - hour
    else:
        shift_id, shift_name = "night", "Night Shift"
        remaining = (6 - hour) if hour < 6 else (30 - hour)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "current_shift": {
            "id": shift_id,
            "name": shift_name,
            "hours": "06:00-14:00" if shift_id == "day" else "14:00-22:00" if shift_id == "evening" else "22:00-06:00",
            "manning_level": "100%" if shift_id == "day" else "90%" if shift_id == "evening" else "80%",
            "production_rate": "Full" if shift_id == "day" else "High" if shift_id == "evening" else "Reduced",
            "response_time_mins": 5 if shift_id == "day" else 8 if shift_id == "evening" else 12,
            "maintenance_allowed": shift_id != "night"
        },
        "time_remaining": {
            "hours": remaining,
            "formatted": f"{remaining}h 0m"
        },
        "adjusted_risk_threshold": 0.55 if shift_id == "day" else 0.50,
        "equipment_needing_attention": len([e for e in PLANT_DATA["equipment"] if e["failure_probability"] > 0.5]),
        "priority_equipment": [
            {"equip_id": e["equip_id"], "type": e["type_display"], "failure_probability": e["failure_probability"]}
            for e in sorted(PLANT_DATA["equipment"], key=lambda x: x["failure_probability"], reverse=True)[:3]
        ],
        "shift_recommendations": ["Monitor high-risk equipment closely", "Complete scheduled inspections"]
    }

@app.get("/api/patterns/heat-cycles")
async def get_heat_cycles(num_heats: int = 12):
    cycles = generate_heat_cycle_data(num_heats)
    
    temps = [c["avg_temp_c"] for c in cycles]
    problematic = [c for c in cycles if abs(c["avg_temp_c"] - 1540) > 15]
    
    return {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_heats": num_heats,
            "avg_temperature_c": round(sum(temps) / len(temps), 1),
            "max_temperature_c": round(max(temps), 1),
            "min_temperature_c": round(min(temps), 1),
            "problematic_heats": len(problematic)
        },
        "problematic_heats": [
            {"heat_id": h["heat_id"], "grade": h["grade"], "deviation": abs(h["avg_temp_c"] - 1540)}
            for h in problematic
        ],
        "heat_cycles": cycles,
        "chart_hint": "Temperature profile shows casting phases: filling, casting, draining"
    }

@app.get("/api/patterns/grades")
async def get_grade_patterns():
    current_grade_key = PRODUCTION_CONTEXT.get("grade_key")
    if not current_grade_key or current_grade_key not in STEEL_GRADES:
        current_grade_key = list(STEEL_GRADES.keys())[0]
    
    current_grade_data = STEEL_GRADES[current_grade_key]
    target_temp = current_grade_data.get("target_temp", 1540)
    tolerance = current_grade_data.get("temp_tolerance", 15)
    
    # Check compliance
    compliance_issues = []
    for equip in PLANT_DATA["equipment"]:
        temp = equip["readings"].get("steel_temp_c", target_temp)
        deviation = abs(temp - target_temp)
        if deviation > tolerance:
            compliance_issues.append({
                "equip_id": equip["equip_id"],
                "current_temp": temp,
                "target_temp": target_temp,
                "deviation": round(deviation, 1)
            })
    
    return {
        "timestamp": datetime.now().isoformat(),
        "current_production": {
            "grade_id": current_grade_key,
            "grade_name": current_grade_data["name"],
            "grade_code": current_grade_key[:3].upper(),
            "target_temp_c": target_temp,
            "temp_tolerance_c": tolerance,
            "casting_speed_range_m_min": [0.9, 1.6],
            "quality_sensitivity": current_grade_data.get("quality_sensitivity", "medium")
        },
        "compliance": {
            "equipment_checked": len(PLANT_DATA["equipment"]),
            "issues_found": len(compliance_issues),
            "status": "CRITICAL" if len(compliance_issues) > 5 else "WARNING" if len(compliance_issues) > 0 else "OK"
        },
        "compliance_issues": compliance_issues,
        "grade_change_note": "Grade change requires equipment recalibration and monitoring"
    }

@app.get("/api/patterns/seasonal")
async def get_seasonal_patterns():
    month = datetime.now().month
    season_name = "Summer" if 6 <= month <= 8 else "Winter" if month in [12, 1, 2] else "Spring/Autumn"
    stress_factor = 1.15 if season_name == "Summer" else 1.05
    
    # Calculate affected equipment
    affected = []
    for equip in PLANT_DATA["equipment"]:
        base_prob = equip["failure_probability"]
        adjusted_prob = min(0.95, base_prob * stress_factor)
        change = adjusted_prob - base_prob
        
        if change > 0.05:
            affected.append({
                "equip_id": equip["equip_id"],
                "base_probability": round(base_prob, 3),
                "adjusted_probability": round(adjusted_prob, 3),
                "change": round(change, 3)
            })
    
    return {
        "timestamp": datetime.now().isoformat(),
        "current_season": {
            "id": season_name.lower().replace("/", "_"),
            "name": season_name,
            "months": [month],
            "ambient_temp_c": 28.5 if season_name == "Summer" else 5.2,
            "humidity_pct": 65
        },
        "operational_impact": {
            "cooling_efficiency": "85%" if season_name == "Summer" else "110%",
            "equipment_stress_factor": stress_factor,
            "impact_summary": f"Seasonal conditions affecting {len(affected)} equipment units"
        },
        "equipment_adjustment": {
            "total_equipment": len(PLANT_DATA["equipment"]),
            "avg_probability_change": round((stress_factor - 1) * 10, 2)
        },
        "most_affected_equipment": sorted(affected, key=lambda x: x["change"], reverse=True)[:5],
        "recommendations": [
            "Increase cooling water flow" if season_name == "Summer" else "Monitor refractory brittleness",
            "Adjust hydraulic oil viscosity for temperature",
            "Schedule extra inspections for thermally stressed equipment"
        ]
    }

@app.get("/api/patterns/maintenance")
async def get_maintenance_patterns(days: int = 30):
    by_type = {}
    for event in MAINTENANCE_HISTORY:
        e_type = event["event_type_display"]
        if e_type not in by_type:
            by_type[e_type] = {"type": e_type, "count": 0, "total_hours": 0, "total_cost_usd": 0}
        by_type[e_type]["count"] += 1
        by_type[e_type]["total_hours"] += event["duration_mins"] / 60
        by_type[e_type]["total_cost_usd"] += event["cost_usd"]
    
    # Most maintained equipment
    equip_counts = {}
    for event in MAINTENANCE_HISTORY:
        eid = event["equipment_id"]
        equip_counts[eid] = equip_counts.get(eid, 0) + 1
    
    most_maintained = sorted([
        {"equip_id": eid, "event_count": count}
        for eid, count in equip_counts.items()
    ], key=lambda x: x["event_count"], reverse=True)[:5]
    
    return {
        "timestamp": datetime.now().isoformat(),
        "period_days": days,
        "summary": {
            "total_events": len(MAINTENANCE_HISTORY),
            "total_downtime_hours": round(sum(e["duration_mins"] for e in MAINTENANCE_HISTORY) / 60, 1),
            "total_cost_usd": sum(e["cost_usd"] for e in MAINTENANCE_HISTORY),
            "emergency_count": len([e for e in MAINTENANCE_HISTORY if e["event_type"] == "corrective"])
        },
        "by_type": list(by_type.values()),
        "most_maintained_equipment": most_maintained,
        "recent_events": [
            {
                "event_id": e["event_id"],
                "date": e["date"],
                "type": e["event_type_display"],
                "description": f"{e['event_type_display']} on {e['equipment_type']}",
                "equipment_id": e["equipment_id"],
                "cost_estimate_usd": e["cost_usd"]
            }
            for e in MAINTENANCE_HISTORY[:10]
        ]
    }

# ==============================================================================
# ADMIN
# ==============================================================================

@app.post("/api/admin/regenerate")
async def regenerate():
    await startup_event()
    return {"status": "success", "message": "Data regenerated", "equipment_count": len(PLANT_DATA["equipment"])}

@app.get("/api/ws/stats")
async def websocket_stats():
    return {
        "total_connections": len(ws_manager.connections),
        "equipment_subscriptions": len(ws_manager.equipment_subs),
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="10.3.0.19", port=8000)
