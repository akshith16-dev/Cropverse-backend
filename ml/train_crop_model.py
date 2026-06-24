"""Train the small, portable baseline crop recommendation model.

Run from cbackend: ``python -m ml.train_crop_model``.
"""
from pathlib import Path
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer

MODEL_PATH = Path(__file__).with_name("crop_model.joblib")

SAMPLES = [
    ("black", "Telangana", "kharif", "Cotton"), ("black", "Telangana", "kharif", "Soybean"),
    ("red", "Telangana", "rabi", "Chickpea"), ("red", "Andhra Pradesh", "kharif", "Groundnut"),
    ("alluvial", "Andhra Pradesh", "rabi", "Rice"), ("clay", "Telangana", "kharif", "Rice"),
    ("loamy", "Telangana", "rabi", "Maize"), ("loamy", "Andhra Pradesh", "rabi", "Tomato"),
    ("sandy", "Andhra Pradesh", "summer", "Watermelon"), ("black", "Andhra Pradesh", "rabi", "Sunflower"),
    ("red", "Telangana", "summer", "Millet"), ("loamy", "Telangana", "kharif", "Maize"),
]

def train() -> Pipeline:
    # ColumnTransformer selects by column name, so preserve feature names in a DataFrame.
    features = pd.DataFrame([{"soil_type": soil, "district": district, "season": season, "land_acres": 2.0} for soil, district, season, _ in SAMPLES])
    labels = [crop for *_, crop in SAMPLES]
    preprocessor = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), ["soil_type", "district", "season"]),
        ("numeric", "passthrough", ["land_acres"]),
    ])
    model = Pipeline([("prep", preprocessor), ("forest", RandomForestClassifier(n_estimators=150, random_state=42))])
    model.fit(features, labels)
    joblib.dump(model, MODEL_PATH)
    return model

if __name__ == "__main__":
    train()
    print(f"Saved {MODEL_PATH}")
