"""Train two baseline models. Split occurs BEFORE fitting preprocessing to avoid leakage."""
from pathlib import Path
import json
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier

ROOT = Path(__file__).parent
(ROOT/'models').mkdir(exist_ok=True)

def train(file, target, numeric, categorical, model, name):
    df = pd.read_csv(ROOT/'data'/file)
    X, y = df.drop(columns=[target]), df[target]
    # Holdout first. Imputers, encoders, scaler and feature selector fit only on X_train.
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.2, random_state=42, stratify=y)
    numeric_pipe = Pipeline([('imputer', SimpleImputer(strategy='median')), ('scaler', StandardScaler())])
    categorical_pipe = Pipeline([('imputer', SimpleImputer(strategy='most_frequent')), ('onehot', OneHotEncoder(handle_unknown='ignore'))])
    prep = ColumnTransformer([('num', numeric_pipe, numeric), ('cat', categorical_pipe, categorical)])
    pipe = Pipeline([('preprocess', prep), ('select', SelectKBest(score_func=f_classif, k=10)), ('model', model)])
    pipe.fit(X_train, y_train)
    pred = pipe.predict(X_test)
    transformed_count = int(pipe.named_steps['preprocess'].transform(X_train).shape[1])
    retained_count = int(pipe.named_steps['select'].get_support().sum())
    metrics = {'dataset':file,'rows':int(df.shape[0]),'columns':int(df.shape[1]),'features_before_selection':transformed_count,'features_after_selection':retained_count,'accuracy':round(float(accuracy_score(y_test,pred)),4),'report':classification_report(y_test,pred,output_dict=True,zero_division=0)}
    joblib.dump(pipe, ROOT/'models'/f'{name}.joblib')
    return metrics

if __name__ == '__main__':
    results = {
      'general': train('general_fitness.csv','recommended_intensity',['age','height_m','weight_kg','bmi','sleep_hours','weekly_exercise_days'],['activity_level','fitness_goal'],RandomForestClassifier(n_estimators=180,random_state=42,class_weight='balanced'),'general_fitness'),
      'inclusive': train('inclusive_activity.csv','suggested_activity',['session_minutes'],['support_preference','mobility_level','experience_level','assistance_preference','energy_level'],DecisionTreeClassifier(max_depth=6,min_samples_leaf=5,class_weight='balanced',random_state=42),'inclusive_activity')
    }
    (ROOT/'models'/'metrics.json').write_text(json.dumps(results,indent=2))
    print(json.dumps({k:{'accuracy':v['accuracy'],'rows':v['rows']} for k,v in results.items()},indent=2))
