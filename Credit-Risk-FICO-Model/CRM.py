import numpy as np 
import pandas as pd 
import matplotlib.pyplot as plt 

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

df = pd.read_csv(r"C:\Users\Startklar\Documents\Milan\Becoming a quant\Quant Projects - Jan 26 onwards\JPM - Qr\Task 3 and 4_Loan_Data.csv")

Target = df["default"]
ID_col = df["customer_id"]

X = df.drop(columns=["default", "customer_id"])
y = df["default"].astype(int)

X = X.fillna(X.median(numeric_only = True))


#Train, Test Split
X_train, X_test, y_train, y_test, = train_test_split(
    X, y, 
    test_size= 0.2, 
    stratify= y, 
    random_state= 42 )

##### Different Models 
models = {}

#Logistic Regression
models["Logistic"] = Pipeline([
    ("scaler", StandardScaler()), 
    ("clf", LogisticRegression(max_iter= 500, class_weight= "balanced"))
])

#Ridge Regression 
models["Ridge"] = Pipeline([
    ("scaler", StandardScaler()), 
    ("clf", LogisticRegression(penalty="l2", max_iter= 500, class_weight= "balanced"))
])

#Lasso Regression (L1)
models["Lasso"] = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", LogisticRegression(
        penalty="l1", solver="saga", max_iter=500, class_weight="balanced"))
])

#Elastic Net 
models["ElasticNet"] = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", LogisticRegression(
        penalty="elasticnet", solver="saga", l1_ratio=0.5, max_iter=500, class_weight="balanced"))
])

#Random Forest 
models["RandomForest"] = RandomForestClassifier(
    n_estimators=400, min_samples_leaf=10, class_weight="balanced", random_state=42)

##### Results
results = {}

for name, model in models.items():
    model.fit(X_train, y_train)
    pd_test = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, pd_test)
    results[name] = auc
    print(f"{name:15s} AUC: {auc:.4f}")

##### Best Model 
best_model_name = max(results, key=results.get)
best_model = models[best_model_name]

print("\nBest model:", best_model_name)

##### Expected Loss Function
def expected_loss(credit_lines_outstanding, loan_amt_outstanding, total_debt_outstanding, income, years_employed, fico_score, recovery_rate=0.10):
    # Expected Loss = PD * LGD  * EAD
    lgd = 1.0 - recovery_rate
    ead = loan_amt_outstanding

    row = pd.DataFrame([{
        "credit_lines_outstanding": credit_lines_outstanding,
        "loan_amt_outstanding": loan_amt_outstanding,
        "total_debt_outstanding": total_debt_outstanding,
        "income": income,
        "years_employed": years_employed,
        "fico_score": fico_score }])

    pd_hat = float(best_model.predict_proba(row)[:, 1])
    return pd_hat * lgd * ead

# Test 
sample = df.iloc[0]
el = expected_loss(credit_lines_outstanding=sample["credit_lines_outstanding"], loan_amt_outstanding=sample["loan_amt_outstanding"], total_debt_outstanding=sample["total_debt_outstanding"], income=sample["income"], years_employed=sample["years_employed"], fico_score=sample["fico_score"], )
print("Expected Loss:", el)

##### FICO Score Bucketting 
df_quant = df[["fico_score", "default"]].copy()
df_quant = df_quant.sort_values("fico_score").reset_index(drop=True)

def build_fico_rating_map(df, n_buckets=5): #FICO Scores into brackets 
    df = df.copy()

    #Create bucket 
    df["bucket"] = pd.qcut(df["fico_score"], q = n_buckets, duplicates= "drop")

    #Bucket Statistics 
    bucket_stats = (df.groupby("bucket").agg(
        min_fico =("fico_score", "min"), max_fico=("fico_score", "max"), default_rate = ("default", "mean"), count = ("default", "size")).reset_index(drop= True))
    
    bucket_stats = bucket_stats.sort_values("default_rate").reset_index(drop= True)
    bucket_stats["rating"] = np.arange(1, len(bucket_stats) + 1)
    return bucket_stats

##### Score Mapping 
rating_map = build_fico_rating_map(df_quant, n_buckets=5)
rating_map

#Rating assignment function
def fico_to_rating(fico_score, rating_map):
    row = rating_map[ (rating_map["min_fico"] <= fico_score) & (fico_score <= rating_map["max_fico"]) ]

    if len(row) == 0:
        return np.nan
    return int(row["rating"].iloc[0])

#Test
fico_to_rating(720, rating_map)