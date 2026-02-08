"""
Prediction Engine with Random Forest Model and SHAP Explanations
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from typing import Dict, List
import warnings
import shap
warnings.filterwarnings('ignore')


class SteelPredictor:
    """Predictive maintenance model using Random Forest"""
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.explainer = None
        self._train_model()
    
    def _train_model(self):
        """Train Random Forest on synthetic failure data"""
        np.random.seed(42)
        n_samples = 1000
        
        # Features that indicate failure risk
        data = {
            'clogging_index': np.random.uniform(0, 100, n_samples),
            'refractory_mm': np.random.uniform(30, 200, n_samples),
            'wear_pct': np.random.uniform(0, 100, n_samples),
            'erosion_pct': np.random.uniform(0, 100, n_samples),
            'age_heats': np.random.uniform(0, 150, n_samples),
            'heats_sequence': np.random.uniform(0, 12, n_samples),
            'temp_deviation': np.random.uniform(-50, 50, n_samples),
            'level_variation_mm': np.random.uniform(0, 15, n_samples),
            'opening_pct': np.random.uniform(20, 100, n_samples),
            'usage_hours': np.random.uniform(0, 8, n_samples),
        }
        
        df = pd.DataFrame(data)
        
        # Create target based on realistic failure rules
        failure_score = (
            (df['clogging_index'] / 100) * 0.25 +
            (1 - df['refractory_mm'] / 200) * 0.20 +
            (df['wear_pct'] / 100) * 0.15 +
            (df['erosion_pct'] / 100) * 0.12 +
            (df['age_heats'] / 150) * 0.10 +
            (df['heats_sequence'] / 12) * 0.08 +
            (df['level_variation_mm'] / 15) * 0.05 +
            (df['opening_pct'] / 100) * 0.05
        )
        
        # Add noise and create binary target
        failure_score += np.random.normal(0, 0.1, n_samples)
        y = (failure_score > 0.45).astype(int)
        
        self.feature_names = list(df.columns)
        X_scaled = self.scaler.fit_transform(df)
        
        # Train Random Forest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            class_weight='balanced',
            random_state=42
        )
        self.model.fit(X_scaled, y)
        
        # Create SHAP explainer
        self.explainer = shap.TreeExplainer(self.model)
        print("✅ Random Forest model trained")
    
    def _prepare_features(self, readings: Dict) -> pd.DataFrame:
        """Convert equipment readings to model features"""
        features = {}
        features['clogging_index'] = readings.get('clogging_index', 0)
        features['refractory_mm'] = readings.get('refractory_mm', 150)
        features['wear_pct'] = readings.get('wear_pct', readings.get('plate_wear_pct', 0))
        features['erosion_pct'] = readings.get('erosion_pct', 0)
        features['age_heats'] = readings.get('age_heats', 0)
        features['heats_sequence'] = readings.get('heats_sequence', 0)
        steel_temp = readings.get('steel_temp_c', 1540)
        features['temp_deviation'] = steel_temp - 1540
        features['level_variation_mm'] = readings.get('level_variation_mm', 0)
        features['opening_pct'] = readings.get('opening_pct', readings.get('gate_position_pct', 50))
        features['usage_hours'] = readings.get('usage_hours', readings.get('operating_hours', 0) / 100)
        
        return pd.DataFrame([features])[self.feature_names]
    
    def predict(self, readings: Dict) -> float:
        """Predict failure probability for equipment"""
        X = self._prepare_features(readings)
        X_scaled = self.scaler.transform(X)
        prob = self.model.predict_proba(X_scaled)[0][1]
        return round(float(prob), 3)
    
    def calculate_shap_values(self, readings: Dict, failure_prob: float = None) -> List[Dict]:
        """Calculate SHAP values for the prediction"""
        X = self._prepare_features(readings)
        X_scaled = self.scaler.transform(X)
        
        shap_values = self.explainer.shap_values(X_scaled)
        
        # Handle different SHAP output formats
        if isinstance(shap_values, list):
            sv = shap_values[1][0]  # Binary classification: positive class
        elif len(shap_values.shape) == 3:
            sv = shap_values[0, :, 1]
        else:
            sv = shap_values[0]
        
        sv = np.array(sv).flatten()
        
        shap_features = []
        for i, feature in enumerate(self.feature_names):
            shap_val = float(sv[i])
            original_val = float(X.iloc[0][feature])
            
            display_name = feature.replace('_', ' ').title()
            if feature == 'temp_deviation':
                display_name = 'Temperature Deviation'
                original_val = readings.get('steel_temp_c', 1540)
            
            shap_features.append({
                'feature': feature,
                'display_name': display_name,
                'value': round(original_val, 2),
                'shap_value': round(shap_val, 4),
                'direction': 'increases_risk' if shap_val > 0 else 'decreases_risk'
            })
        
        shap_features.sort(key=lambda x: abs(x['shap_value']), reverse=True)
        return shap_features[:5]


# Global predictor instance
_predictor = None

def get_predictor() -> SteelPredictor:
    """Get or create the global predictor instance"""
    global _predictor
    if _predictor is None:
        _predictor = SteelPredictor()
    return _predictor
