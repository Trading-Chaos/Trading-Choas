from adapters.xgb_adapter import XGBAdapter

def get_model(name: str):

    if name == "xgb_ttp":
        return XGBAdapter(
            artifact_dir="src/MLbridg/artifacts/xgb_ttp"
        )

    raise ValueError(f"Unknown model: {name}")