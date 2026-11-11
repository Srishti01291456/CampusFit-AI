"""Generate reproducible, clearly-labelled demo datasets for CampusFit AI.
These are synthetic educational records, not clinical or real-person data.
"""
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).parent / 'data'
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(42)
n = 1200
age = rng.integers(18, 61, n)
height = rng.normal(1.68, .10, n).clip(1.42, 2.02)
weight = rng.normal(70, 15, n).clip(42, 125)
bmi = weight / height**2
activity = rng.choice(['low', 'moderate', 'high'], n, p=[.38, .44, .18])
sleep = rng.normal(7, 1.2, n).clip(3.5, 10)
frequency = np.array([rng.integers(0, 2) if x == 'low' else rng.integers(2, 5) if x == 'moderate' else rng.integers(4, 7) for x in activity])
goal = rng.choice(['general_fitness', 'strength', 'flexibility', 'weight_management'], n)
# Educational target rules introduce learnable patterns, not medical recommendations.
score = (frequency * .55 + (activity == 'high') * 1.2 + (goal == 'strength') * .6 + (goal == 'flexibility') * .2 + (sleep >= 7) * .35 - (bmi >= 30) * .35)
intensity = np.where(score >= 3.2, 'active', np.where(score >= 1.5, 'moderate', 'gentle'))
normal = pd.DataFrame({'age':age,'height_m':height.round(2),'weight_kg':weight.round(1),'bmi':bmi.round(1),'activity_level':activity,'sleep_hours':sleep.round(1),'weekly_exercise_days':frequency,'fitness_goal':goal,'recommended_intensity':intensity})
# Add small realistic missingness for preprocessing demonstration.
for col in ['sleep_hours','activity_level','weight_kg','fitness_goal']:
    normal.loc[rng.choice(n, 18, replace=False), col] = np.nan
normal.to_csv(OUT/'general_fitness.csv', index=False)

m = 1000
support = rng.choice(['cognitive_support','physical_accessibility'], m, p=[.48,.52])
experience = rng.choice(['beginner','some_experience','experienced'], m, p=[.55,.32,.13])
mobility = rng.choice(['seated','limited_mobility','independent'], m, p=[.32,.28,.40])
minutes = rng.integers(5, 36, m)
assistance = rng.choice(['guided','some_support','independent'], m, p=[.42,.30,.28])
energy = rng.choice(['low','medium','high'], m, p=[.25,.50,.25])
# Curated educational labels; final exercise options are reviewed, not autonomously prescribed.
labels=[]
for s, mob, mins, assist, en, exp in zip(support,mobility,minutes,assistance,energy,experience):
    if s == 'physical_accessibility':
        labels.append('seated_mobility' if mob == 'seated' or mins <= 10 else ('supported_movement' if mob == 'limited_mobility' or assist != 'independent' else 'low_impact_movement'))
    else:
        labels.append('short_step_guided' if mins <= 12 or en == 'low' or assist == 'guided' else ('repeatable_routine' if exp == 'beginner' else 'mindful_movement'))
inclusive = pd.DataFrame({'support_preference':support,'mobility_level':mobility,'experience_level':experience,'session_minutes':minutes,'assistance_preference':assistance,'energy_level':energy,'suggested_activity':labels})
for col in ['experience_level','session_minutes','energy_level']:
    inclusive.loc[rng.choice(m, 12, replace=False), col] = np.nan
inclusive.to_csv(OUT/'inclusive_activity.csv', index=False)
print(f'Wrote {len(normal)} general and {len(inclusive)} inclusive synthetic demo rows.')
