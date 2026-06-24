"""Lazy crop recommendation model loader and explainable result helper."""
from pathlib import Path
import joblib
import pandas as pd
from .train_crop_model import MODEL_PATH, train

_model = None

def get_model():
    global _model
    if _model is None:
        _model = joblib.load(MODEL_PATH) if Path(MODEL_PATH).exists() else train()
    return _model

def recommend(soil_type: str, district: str, season: str, land_acres: float) -> dict:
    sample = pd.DataFrame([{"soil_type": soil_type.strip().lower(), "district": district.strip(), "season": season.strip().lower(), "land_acres": land_acres}])
    model = get_model()
    probabilities = model.predict_proba(sample)[0]
    index = probabilities.argmax()
    crop = model.classes_[index]
    confidence = round(float(probabilities[index]), 2)
    return {
        "crop": crop,
        "recommended_crop": crop,
        "confidence": confidence,
        "explanation": f"{crop} is a strong baseline match for {soil_type} soil during {season} in {district}.",
        "reasons": [
            f"The model has seen {soil_type} soil paired with this crop.",
            f"The {season} season is suitable for this recommendation.",
            f"Your {land_acres:g}-acre holding can be planned in manageable blocks.",
        ],
    }
