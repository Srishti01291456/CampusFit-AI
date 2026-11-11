from pathlib import Path
import sqlite3, json, os
import joblib
import pandas as pd
from flask import Flask, render_template, request, jsonify, g

ROOT = Path(__file__).parent
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY','campusfit-local-demo-key')
DB = ROOT/'campusfit.db'
MODELS = ROOT/'models'

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None: db.close()

@app.before_request
def init_db():
    db=get_db()
    db.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, kind TEXT, value REAL, note TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    db.execute('CREATE TABLE IF NOT EXISTS favorites (id INTEGER PRIMARY KEY, exercise TEXT UNIQUE)')
    db.execute('CREATE TABLE IF NOT EXISTS stories (id INTEGER PRIMARY KEY, title TEXT, note TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    db.execute('''CREATE TABLE IF NOT EXISTS support_contacts (
        contact_key TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        phone TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.commit()

@app.get('/api/rewards')
def rewards():
    db=get_db()
    activity=float(db.execute("SELECT COALESCE(SUM(value),0) FROM logs WHERE kind='activity'").fetchone()[0])
    water=float(db.execute("SELECT COALESCE(SUM(value),0) FROM logs WHERE kind='water'").fetchone()[0])
    moods=int(db.execute("SELECT COUNT(*) FROM logs WHERE kind='mood'").fetchone()[0])
    stories=int(db.execute("SELECT COUNT(*) FROM stories").fetchone()[0])
    points=int(activity*2 + water//250 + stories*5)
    badges=[]
    if activity>=30: badges.append({'icon':'🏃','name':'Movement Starter','detail':'Logged 30 activity minutes'})
    if water>=1000: badges.append({'icon':'💧','name':'Hydration Habit','detail':'Logged 1,000 ml of water'})
    if stories>=1: badges.append({'icon':'🌱','name':'First Small Win','detail':'Saved your first story'})
    if moods>=5: badges.append({'icon':'💚','name':'Mindful Check-ins','detail':'Completed 5 mood check-ins'})
    if not badges: badges.append({'icon':'✨','name':'Your first reward is waiting','detail':'Log activity, water or a story to unlock a badge'})
    return jsonify({'points':points,'activity_minutes':activity,'water_ml':water,'stories':stories,'mood_checkins':moods,'badges':badges})

def get_models():
    general = joblib.load(MODELS/'general_fitness.joblib') if (MODELS/'general_fitness.joblib').exists() else None
    inclusive = joblib.load(MODELS/'inclusive_activity.joblib') if (MODELS/'inclusive_activity.joblib').exists() else None
    return general, inclusive

@app.get('/')
def home(): return render_template('index.html')

@app.get('/api/summary')
def summary():
    db=get_db()
    rows=db.execute("SELECT kind, SUM(value) total FROM logs WHERE date(created_at,'localtime')=date('now','localtime') GROUP BY kind").fetchall()
    totals={r['kind']:r['total'] or 0 for r in rows}
    history=db.execute("SELECT date(created_at,'localtime') day, SUM(CASE WHEN kind='activity' THEN value ELSE 0 END) activity, SUM(CASE WHEN kind='water' THEN value ELSE 0 END) water, AVG(CASE WHEN kind='mood' THEN value END) mood FROM logs GROUP BY date(created_at,'localtime') ORDER BY day DESC LIMIT 7").fetchall()
    fav=[r['exercise'] for r in db.execute('SELECT exercise FROM favorites').fetchall()]
    points_today=int((totals.get('activity',0) or 0)*2 + (totals.get('water',0) or 0)//250*1)
    story_count=db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    points_lifetime=int(db.execute("SELECT COALESCE(SUM(CASE WHEN kind='activity' THEN value*2 WHEN kind='water' THEN value/250 ELSE 0 END),0) FROM logs").fetchone()[0]) + story_count*5
    return jsonify({'today':totals,'history':[dict(x) for x in reversed(history)],'favorites':fav,'points':points_today,'lifetime_points':points_lifetime,'stories':story_count})

@app.post('/api/log')
def log_entry():
    data=request.get_json(force=True); kind=data.get('kind'); value=float(data.get('value',0)); note=str(data.get('note',''))[:200]
    if kind not in ('water','activity','mood') or value<0 or value>10000: return jsonify({'error':'Invalid entry'}),400
    db=get_db(); db.execute('INSERT INTO logs(kind,value,note) VALUES(?,?,?)',(kind,value,note)); db.commit()
    return jsonify({'ok':True})

@app.post('/api/favorite')
def favorite():
    name=str(request.get_json(force=True).get('exercise',''))[:100]
    if not name:return jsonify({'error':'Exercise required'}),400
    db=get_db(); found=db.execute('SELECT id FROM favorites WHERE exercise=?',(name,)).fetchone()
    if found: db.execute('DELETE FROM favorites WHERE exercise=?',(name,)); state=False
    else: db.execute('INSERT INTO favorites(exercise) VALUES(?)',(name,)); state=True
    db.commit(); return jsonify({'favorite':state})

@app.post('/api/story')
def story():
    data=request.get_json(force=True); title=str(data.get('title','My progress'))[:80]; note=str(data.get('note',''))[:500]
    if not note.strip(): return jsonify({'error':'Write a short update first'}),400
    db=get_db(); db.execute('INSERT INTO stories(title,note) VALUES(?,?)',(title,note)); db.commit(); return jsonify({'ok':True})

@app.get('/api/stories')
def stories():
    return jsonify([dict(x) for x in get_db().execute('SELECT title,note,created_at FROM stories ORDER BY id DESC LIMIT 10').fetchall()])

@app.get('/api/contacts')
def get_contacts():
    rows = get_db().execute(
        'SELECT contact_key, label, phone FROM support_contacts'
    ).fetchall()
    return jsonify({row['contact_key']: dict(row) for row in rows})

@app.post('/api/contacts')
def save_contact():
    data = request.get_json(force=True)
    key = str(data.get('contact_key', '')).strip()
    phone = str(data.get('phone', '')).strip()
    labels = {
        'male_counsellor': 'Male counsellor',
        'female_counsellor': 'Female counsellor',
        'consultant': 'Personal consultant',
        'dietitian': 'Dietitian'
    }
    if key not in labels:
        return jsonify({'error': 'Unknown contact type.'}), 400
    if phone and (len(phone) < 7 or len(phone) > 20 or not all(c in '+0123456789 ()-' for c in phone)):
        return jsonify({'error': 'Enter a valid phone number, or leave it blank to clear it.'}), 400
    db = get_db()
    db.execute('''INSERT INTO support_contacts(contact_key, label, phone, updated_at)
                  VALUES(?,?,?,CURRENT_TIMESTAMP)
                  ON CONFLICT(contact_key) DO UPDATE SET
                  label=excluded.label, phone=excluded.phone,
                  updated_at=CURRENT_TIMESTAMP''',
               (key, labels[key], phone))
    db.commit()
    return jsonify({'ok': True, 'contact_key': key, 'phone': phone})

@app.post('/api/predict/general')
def predict_general():
    model,_=get_models()
    if model is None:return jsonify({'error':'Models missing. Run python train_models.py'}),503
    d=request.get_json(force=True)
    try:
        row=pd.DataFrame([{'age':int(d['age']),'height_m':float(d['height_m']),'weight_kg':float(d['weight_kg']),'bmi':float(d['weight_kg'])/(float(d['height_m'])**2),'activity_level':d['activity_level'],'sleep_hours':float(d['sleep_hours']),'weekly_exercise_days':int(d['weekly_exercise_days']),'fitness_goal':d['fitness_goal']}])
        if not 15<=row.age.iloc[0]<=90 or not 1.2<=row.height_m.iloc[0]<=2.3 or not 25<=row.weight_kg.iloc[0]<=250: raise ValueError()
    except Exception:return jsonify({'error':'Please enter valid profile values.'}),400
    result=model.predict(row)[0]
    return jsonify({'prediction':result,'message':{'gentle':'Start with comfortable, low-intensity movement and build gradually.','moderate':'A balanced moderate routine may fit your selected profile.','active':'Your profile matches the active category in this demo model.'}.get(result,''),'disclaimer':'Educational prediction only; not medical advice. Adjust activity to your comfort and seek professional guidance when needed.'})

@app.post('/api/predict/inclusive')
def predict_inclusive():
    _,model=get_models()
    if model is None:return jsonify({'error':'Models missing. Run python train_models.py'}),503
    d=request.get_json(force=True)
    allowed={'support_preference':['cognitive_support','physical_accessibility'],'mobility_level':['seated','limited_mobility','independent'],'experience_level':['beginner','some_experience','experienced'],'assistance_preference':['guided','some_support','independent'],'energy_level':['low','medium','high']}
    try:
        for k,vals in allowed.items():
            if d[k] not in vals: raise ValueError()
        minutes=int(d['session_minutes'])
        if not 5<=minutes<=60: raise ValueError()
    except Exception:return jsonify({'error':'Please select valid options.'}),400
    row=pd.DataFrame([{'support_preference':d['support_preference'],'mobility_level':d['mobility_level'],'experience_level':d['experience_level'],'session_minutes':minutes,'assistance_preference':d['assistance_preference'],'energy_level':d['energy_level']}])
    pred=model.predict(row)[0]
    descriptions={'seated_mobility':'Gentle seated range-of-motion activity with breaks.','supported_movement':'Low-impact movement with stable support and optional assistance.','low_impact_movement':'Comfort-led low-impact movement; stop if uncomfortable.','short_step_guided':'A short, one-step-at-a-time guided movement routine.','repeatable_routine':'A simple repeatable routine with clear steps and reminders.','mindful_movement':'A calm, mindful movement session with predictable instructions.'}
    return jsonify({'prediction':pred.replace('_',' ').title(),'message':descriptions[pred],'disclaimer':'This is a demo recommendation, not a diagnosis or therapy plan. Choose only activities that are safe and comfortable for you; consult a qualified professional when appropriate.'})

@app.post('/api/coach')
def coach():
    data=request.get_json(force=True)
    q=str(data.get('message','')).lower().strip()
    profile=str(data.get('profile','normal'))
    if not q: return jsonify({'reply':'Tell me what you would like help with.','note':'General wellness information only.'})
    if any(w in q for w in ['emergency','chest pain','cannot breathe','suicide','hurt myself','self harm']):
        answer='This chat is not monitored and cannot provide emergency help. If you may be in immediate danger, contact local emergency services now. In India, call 112 for emergency assistance. If you are thinking about harming yourself, reach out to a trusted person and a qualified crisis or mental-health service immediately.'
    elif any(w in q for w in ['tired','low energy','exhausted','fatigue']):
        answer='It is okay to make today a lighter day. Consider a rest break, water if appropriate, and a shorter activity or no activity at all. If tiredness is new, severe or persistent, discuss it with a qualified clinician.'
    elif any(w in q for w in ['water','hydration','drink']):
        answer='You can log water in Nutrition. Keep a drink accessible and sip regularly according to thirst and your personal needs. Fluid needs vary with health, climate and activity; follow any clinician-provided fluid limits.'
    elif any(w in q for w in ['veg','vegetarian','paneer','dal','plant']):
        answer='Try one of these vegetarian ideas from Nutrition: moong dal chilla, rajma with rice and salad, paneer bhurji with roti, sprouts chaat, or palak paneer. Choose foods and portions that suit your preferences, allergies and dietary advice.'
    elif any(w in q for w in ['non veg','non-veg','chicken','fish','egg']):
        answer='Some non-vegetarian ideas in Nutrition are egg bhurji with roti, grilled chicken with rice and salad, fish curry with vegetables, boiled eggs with fruit, or chicken and vegetable soup. Adapt ingredients for allergies and personal dietary guidance.'
    elif any(w in q for w in ['meal','diet','food','nutrition','breakfast','lunch','dinner','snack']):
        answer='Open Nutrition and choose Vegetarian or Non-vegetarian, then select breakfast, lunch, snack or dinner. Aim for a varied plate with foods you enjoy; the suggestions are examples, not a prescribed diet.'
    elif any(w in q for w in ['wheelchair','seated','mobility','physical','accessible','physio']):
        answer='I have set the app to '+('physical accessibility' if profile=='physical' else 'your current profile')+'. Open Exercises for seated arm movements, shoulder mobility, ankle mobility and supported stretches, each with instructions and a video-search link. Only try movements that are appropriate for you; a physiotherapist can advise on individual safety.'
    elif any(w in q for w in ['memory','cognitive','simple steps','reminder','confused']):
        answer='For cognitive-support routines, open Exercises and choose the Cognitive Support path. The activities use short, predictable instructions, repetition and one step at a time. A trusted supporter can help read the steps if you want.'
    elif any(w in q for w in ['stress','sad','anxious','mood','upset','lonely']):
        answer='Thank you for sharing that. You could choose a calm playlist in Mood Music, take a comfortable pause, or log an optional mood check-in in Insights. If these feelings are overwhelming or persistent, consider talking with someone you trust or a qualified mental-health professional.'
    elif any(w in q for w in ['exercise','workout','movement','routine']):
        answer='Open Exercises to see routines matched to your selected path. Choose a comfortable duration, read the steps first and use the video-search link for a demonstration. Start gently and stop if you feel pain, dizzy or unwell.'
    elif any(w in q for w in ['playlist','music','song']):
        answer='Open Mood Music and choose Calm, Happy, Energetic, Focus, Comfort or Sleep. The buttons open music search results so you can choose a suitable track.'
    elif any(w in q for w in ['consult','doctor','physiotherapist','dietitian','professional','help line','helpline']):
        answer='Open Support for emergency and mental-health support contacts, and save a verified local clinician, physiotherapist or dietitian number. CampusFit does not provide a live consultation service.'
    elif any(w in q for w in ['progress','insight','chart','track']):
        answer='Open Insights to see logged water, activity and mood trends. Log your water and activity in their respective pages and use the mood check-in to build a more complete picture. The charts show only data you have entered.'
    else:
        answer='I can help you navigate exercise routines, meal ideas, hydration, mood-based playlists, progress tracking and support contacts. Tell me which one you want to work on, or choose one of the suggested prompts.'
    return jsonify({'reply':answer,'note':'CampusFit AI provides general educational wellness information, not diagnosis, treatment, therapy or emergency monitoring.'})

@app.post('/api/food')
def food():
    # Lightweight transparent baseline: classify broad image colour/brightness only; never claim nutrition facts.
    from PIL import Image
    import io, numpy as np
    f=request.files.get('image')
    if not f:return jsonify({'error':'Choose an image first.'}),400
    try:
        im=Image.open(io.BytesIO(f.read())).convert('RGB').resize((64,64)); a=np.asarray(im)/255
        mean=a.mean((0,1)); green=float(mean[1]); red=float(mean[0]); blue=float(mean[2])
        if green>red*0.93 and green>blue*1.05: label='Green-dominant food image'
        elif red>green*1.15: label='Red/orange-dominant food image'
        else: label='Mixed-colour food image'
        return jsonify({'label':label,'message':'This is a simple colour-based demo, not a trained food recognizer. It cannot identify ingredients, calories or allergens.'})
    except Exception:return jsonify({'error':'Could not read that image.'}),400

@app.get('/health')
def health(): return jsonify({'status':'ok','models':[(MODELS/'general_fitness.joblib').exists(),(MODELS/'inclusive_activity.joblib').exists()]})

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)
