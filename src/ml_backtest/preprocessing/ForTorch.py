import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from preprocessing.preprocess import prep, append_results
import numpy as np
from metrics.Metrics import merged_metrics
from preprocessing.target import ttp_target

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

def set_seed(seed=42):
    import random, os
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

class SeqDataset(Dataset):
    def __init__(self, X, y, seq_len: int):
        self.X = X.values.astype("float32") if hasattr(X, "values") else X.astype("float32")
        self.y = y.values.astype("int64") if hasattr(y, "values") else y.astype("int64")
        self.seq_len = int(seq_len)

    def __len__(self):
        return max(0, len(self.X) - self.seq_len + 1)

    def __getitem__(self, idx):
        x = self.X[idx : idx + self.seq_len]        # (L, F)
        y = self.y[idx + self.seq_len - 1]          # scalar
        return torch.from_numpy(x), torch.tensor(y)
    
@torch.no_grad()
def torch_predict(model, loader):
    model.eval()
    preds = []
    for xb, _ in loader:
        xb = xb.to(DEVICE)
        logits = model(xb)
        preds.append(torch.argmax(logits, dim=1).detach().cpu().numpy())
    return np.concatenate(preds)

def train_torch_classifier(
    model: nn.Module,
    train_loader: DataLoader,
    test_loader: DataLoader,
    epochs: int = 10,
    lr: float = 1e-3,
    weight_decay: float = 0.0,
):
    model = model.to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    crit = nn.CrossEntropyLoss()

    for ep in range(1, epochs+1):
        model.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            opt.zero_grad()
            logits = model(xb)
            loss = crit(logits, yb)
            loss.backward()
            opt.step()

    y_pred = torch_predict(model, test_loader)
    return y_pred

from pytorch_tabnet.tab_model import TabNetClassifier

def train_tabnet_ttp(df, train_size, test_size, step):
    splitter = prep(
        df=df,
        target_fn=ttp_target,
        target_name="ttp",
        target_col="TTP_class",
        horizons=[12, 24, 48],
        train_size=train_size,
        test_size=test_size,
        step=step,
        target_kwargs={"n_classes": 3},
        scale_cols=[
            "Open","High","Low","Close",
            "Alligator_Jaw","Alligator_Teeth","Alligator_Lips",
            "AO","AddOn_Anchor_Level","AddOn_Size_Pct"
        ]
    )

    for X_train, X_test, y_train, y_test, scaler in splitter:

        model = TabNetClassifier(
            n_d=16, n_a=16, n_steps=5,
            gamma=1.5,
            n_independent=2, n_shared=2,
            seed=42,
            verbose=0
        )

        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            max_epochs=100,
            patience=15,
            batch_size=1024,
            virtual_batch_size=256,
            num_workers=0,
            drop_last=False
        )

        y_pred = model.predict(X_test)
        metrics = merged_metrics(y_test, y_pred)

        append_results({
            "task_type": "classification",
            "model_name": "TabNet",
            "model_family": "tabnet",
            "model_params": {
                "n_d": 16, "n_a": 16, "n_steps": 5, "gamma": 1.5
            },
            "target_name": "ttp",
            "target_variant": "3class",
            "horizons": "12_24_48",
            **metrics
        })