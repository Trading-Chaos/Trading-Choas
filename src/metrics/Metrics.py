import numpy as np
from sklearn.metrics import confusion_matrix, recall_score, precision_score

def ttp_metrics(
    y_true,
    y_pred,
    labels=(0, 1, 2, 3)
):
    metrics = {}

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    metrics["confusion_matrix"] = cm

    recall_vals = recall_score(
        y_true,
        y_pred,
        labels=[0, 1],
        average=None,
        zero_division=0
    )

    metrics["recall_fast"] = recall_vals[0]
    metrics["recall_mid"] = recall_vals[1]
    metrics["recall_fast_mid_mean"] = recall_vals.mean()

    precision_np = precision_score(
        y_true,
        y_pred,
        labels=[3],
        average=None,
        zero_division=0
    )

    metrics["precision_no_profit"] = precision_np[0]

    metrics["support_fast"] = np.sum(y_true == 0)
    metrics["support_mid"] = np.sum(y_true == 1)
    metrics["support_slow"] = np.sum(y_true == 2)
    metrics["support_no_profit"] = np.sum(y_true == 3)

    return metrics