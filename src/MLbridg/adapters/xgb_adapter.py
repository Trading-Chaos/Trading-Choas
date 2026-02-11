import joblib
import pandas as pd
from pathlib import Path
from .base import BaseModelAdapter

class XGBAdapter(BaseModelAdapter):

    def __init__(self, artifact_dir):
        artifact_dir = Path(artifact_dir)

        self.model      = joblib.load(artifact_dir / "model.pkl")
        self.scaler     = joblib.load(artifact_dir / "scaler.pkl")
        self.scale_cols = joblib.load(artifact_dir / "scale_cols.pkl")

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df.drop(columns=["DateTime"], errors="ignore").copy()

        # ⬅️ масштабируем ТОЛЬКО нужные колонки
        X_scaled = self.scaler.transform(X[self.scale_cols])
        X.loc[:, self.scale_cols] = X_scaled

        # ⬅️ подаём в модель ПОЛНЫЙ feature set
        proba = self.model.predict_proba(X)
        pred  = self.model.predict(X)

        out = df.copy()
        out["ML_TTP_CLASS"]  = pred
        out["ML_PROBA_GOOD"] = proba[:, 0]

        return out