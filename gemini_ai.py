"""
Gemini AI Integration for AI-Powered Explanations
"""
import os
from typing import Dict, List

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

_client = None
_init_error = None


def _get_client():
    """Lazy load the Gemini client"""
    global _client, _init_error
    
    if not GEMINI_API_KEY:
        _init_error = "API key not set"
        return None
    
    if _client is None:
        try:
            from google import genai
            _client = genai.Client(api_key=GEMINI_API_KEY)
            _init_error = None
            print("✅ Gemini client initialized")
        except Exception as e:
            _init_error = str(e)
            _client = None
    return _client


def generate_ai_explanation(
    equip_id: str,
    equip_type: str,
    failure_prob: float,
    shap_features: List[Dict],
    readings: Dict,
    use_ai: bool = True
) -> str:
    """Generate AI-powered explanation"""
    
    client = _get_client()
    
    if not use_ai or client is None:
        return _generate_template_explanation(equip_id, equip_type, failure_prob, shap_features, readings)
    
    try:
        prompt = _build_prompt(equip_id, equip_type, failure_prob, shap_features, readings)
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        
        if response and response.text:
            return response.text.strip()
        else:
            return _generate_template_explanation(equip_id, equip_type, failure_prob, shap_features, readings)
    except Exception as e:
        print(f"Gemini API error: {e}")
        return _generate_template_explanation(equip_id, equip_type, failure_prob, shap_features, readings)


def _build_prompt(equip_id: str, equip_type: str, failure_prob: float, shap_features: List[Dict], readings: Dict) -> str:
    """Build prompt for Gemini"""
    risk_level = "HIGH" if failure_prob > 0.7 else "MODERATE" if failure_prob > 0.3 else "LOW"
    
    shap_text = "\n".join([
        f"  - {f['display_name']}: {f['value']:.2f} (impact: {f['shap_value']:+.3f}, {f['direction']})"
        for f in shap_features
    ])
    
    readings_text = "\n".join([
        f"  - {k.replace('_', ' ').title()}: {v:.2f}"
        for k, v in readings.items()
    ])
    
    prompt = f"""You are an expert steel plant maintenance advisor.

EQUIPMENT: {equip_id}
TYPE: {equip_type.replace('_', ' ').title()}
FAILURE PROBABILITY: {failure_prob:.1%}
RISK LEVEL: {risk_level}

CURRENT READINGS:
{readings_text}

AI MODEL ANALYSIS (SHAP features):
{shap_text}

Write a 2-3 sentence explanation that:
1. States the risk level and main concern
2. Explains WHY based on top factors
3. Gives one specific action

Be professional, specific, under 100 words. No bullet points."""
    
    return prompt


def generate_ai_recommendations(
    equip_id: str,
    equip_type: str,
    failure_prob: float,
    readings: Dict,
    shap_features: List[Dict],
    use_ai: bool = True
) -> List[Dict]:
    """Generate AI-powered maintenance recommendations"""
    
    client = _get_client()
    
    if not use_ai or client is None:
        return _generate_rule_based_recommendations(equip_id, equip_type, failure_prob, readings)
    
    try:
        prompt = _build_recommendations_prompt(equip_id, equip_type, failure_prob, readings, shap_features)
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        
        if response and response.text:
            return _parse_recommendations(response.text, failure_prob)
        else:
            return _generate_rule_based_recommendations(equip_id, equip_type, failure_prob, readings)
    except Exception as e:
        print(f"Gemini API error: {e}")
        return _generate_rule_based_recommendations(equip_id, equip_type, failure_prob, readings)


def _build_recommendations_prompt(equip_id: str, equip_type: str, failure_prob: float, readings: Dict, shap_features: List[Dict]) -> str:
    """Build prompt for recommendations"""
    readings_text = "\n".join([f"  - {k}: {v:.2f}" for k, v in readings.items()])
    shap_text = "\n".join([f"  - {f['display_name']}: {f['shap_value']:+.3f}" for f in shap_features[:3]])
    
    prompt = f"""Generate 3 maintenance recommendations.

EQUIPMENT: {equip_id} ({equip_type})
FAILURE PROBABILITY: {failure_prob:.1%}

READINGS:
{readings_text}

TOP RISK FACTORS:
{shap_text}

Generate exactly 3 recommendations in this format (one per line):
PRIORITY|ACTION|URGENCY|TIME_MINS

Example:
1|Inspect SEN nozzle for alumina buildup|immediate|20
2|Increase argon injection flow rate to 8 LPM|soon|5
3|Schedule refractory thickness measurement|planned|30

ONLY output the 3 lines, no other text."""
    
    return prompt


def _parse_recommendations(response_text: str, failure_prob: float) -> List[Dict]:
    """Parse Gemini response"""
    recommendations = []
    
    for line in response_text.strip().split('\n'):
        line = line.strip()
        if '|' in line:
            parts = line.split('|')
            if len(parts) >= 4:
                try:
                    recommendations.append({
                        "priority": int(parts[0].strip()),
                        "action": parts[1].strip(),
                        "reason": "AI-generated recommendation",
                        "urgency": parts[2].strip().lower(),
                        "estimated_time_mins": int(parts[3].strip())
                    })
                except (ValueError, IndexError):
                    continue
    
    if not recommendations:
        return _generate_rule_based_recommendations("", "", failure_prob, {})
    
    return recommendations[:3]


def _generate_template_explanation(equip_id: str, equip_type: str, failure_prob: float, shap_features: List[Dict], readings: Dict) -> str:
    """Fallback template-based explanation"""
    risk_level = "HIGH" if failure_prob > 0.7 else "MODERATE" if failure_prob > 0.3 else "LOW"
    
    explanation = f"{equip_id} shows {risk_level} risk with {failure_prob:.0%} failure probability. "
    
    top_factors = [f for f in shap_features if f["direction"] == "increases_risk"][:3]
    if top_factors:
        factor_strs = []
        for f in top_factors:
            feat = f["feature"]
            val = f["value"]
            if "clogging" in feat:
                factor_strs.append(f"elevated clogging index ({val:.0f})")
            elif "wear" in feat or "erosion" in feat:
                factor_strs.append(f"component wear at {val:.0f}%")
            elif "refractory" in feat:
                factor_strs.append(f"refractory thickness down to {val:.0f}mm")
            elif "heats" in feat:
                factor_strs.append(f"{val:.0f} heats in current sequence")
            else:
                factor_strs.append(f"{f['display_name'].lower()} at {val:.1f}")
        
        if factor_strs:
            explanation += "Primary risk factors: " + ", ".join(factor_strs) + ". "
    
    if failure_prob > 0.7:
        explanation += "Recommend immediate inspection and scheduling maintenance within current shift."
    elif failure_prob > 0.5:
        explanation += "Recommend scheduling inspection within next 4-8 hours."
    elif failure_prob > 0.3:
        explanation += "Monitor closely and plan maintenance for next scheduled downtime."
    else:
        explanation += "Equipment operating within normal parameters."
    
    return explanation


def _generate_rule_based_recommendations(equip_id: str, equip_type: str, failure_prob: float, readings: Dict) -> List[Dict]:
    """Fallback rule-based recommendations"""
    recommendations = []
    priority = 1
    
    if readings.get("clogging_index", 0) > 50:
        recommendations.append({
            "priority": priority,
            "action": "Inspect nozzle for alumina buildup",
            "reason": f"Clogging index at {readings.get('clogging_index', 0):.0f}",
            "urgency": "immediate" if readings.get("clogging_index", 0) > 75 else "soon",
            "estimated_time_mins": 20
        })
        priority += 1
    
    if readings.get("refractory_mm", 200) < 80:
        recommendations.append({
            "priority": priority,
            "action": "Schedule refractory relining",
            "reason": f"Refractory thickness at {readings.get('refractory_mm', 0):.0f}mm",
            "urgency": "immediate" if readings.get("refractory_mm", 200) < 60 else "planned",
            "estimated_time_mins": 240
        })
        priority += 1
    
    if readings.get("wear_pct", 0) > 60 or readings.get("erosion_pct", 0) > 60:
        recommendations.append({
            "priority": priority,
            "action": "Replace worn components",
            "reason": "Component wear detected",
            "urgency": "soon",
            "estimated_time_mins": 60
        })
        priority += 1
    
    if not recommendations:
        recommendations.append({
            "priority": 1,
            "action": "Continue normal monitoring",
            "reason": "Equipment operating within parameters",
            "urgency": "routine",
            "estimated_time_mins": 0
        })
    
    return recommendations
