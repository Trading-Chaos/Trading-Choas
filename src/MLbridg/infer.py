from .registry import get_model

def apply_ml_filter(
    df,
    model_name="xgb_ttp",
    proba_threshold=0.55
):

    model = get_model(model_name)
    df = model.predict(df)

    df["ML_ALLOW_ENTRY"] = (
        (df["ML_TTP_CLASS"] == 0) &
        (df["ML_PROBA_GOOD"] >= proba_threshold)
    )

    return df