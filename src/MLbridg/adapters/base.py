from abc import ABC, abstractmethod
import pandas as pd

class BaseModelAdapter(ABC):

    @abstractmethod
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        MUST return df with columns:
        - ML_TTP_CLASS
        - ML_PROBA_GOOD
        """
        pass