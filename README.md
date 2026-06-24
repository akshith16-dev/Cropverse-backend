# Cropverse
# Cropverse backend

## New platform services

- WebSockets: `/ws/notifications/{user_id}`, `/ws/prices`, `/ws/marketplace`, and `/ws/supply-demand`.
- AI: `POST /ai/recommend-crop`, `POST /ai/predict-demand`, and `POST /ai/predict-price` (all authenticated).
- Admin analytics and downloads: `/analytics/admin`, `/reports/farmers`, `/reports/orders`, `/reports/crops`.
- Authenticated uploads: `POST /upload/image` and `POST /upload/document`. Files are served under `/uploads/` and should be backed by object storage on multi-instance production deployments.

## Run locally

Create a `.env` containing `DATABASE_URL`, `SECRET_KEY`, and `GEMINI_API_KEY`, then install dependencies and start:

```bash
pip install -r requirements.txt
python seed.py
uvicorn main:app --reload
```

Train the persisted baseline crop model explicitly with `python -m ml.train_crop_model`; the API will also create it on its first recommendation request.
