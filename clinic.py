
import sqlite3
import os
import time
import base64
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import africastalking

app = Flask(__name__)
app.secret_key = 'clinic_secret_key_123'

DB_FILE = 'clinic.db'
STAFF_PIN = '1234'
BG_URL = "https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?auto=format&fit=crop&w=800&q=80"

# --- REAL API CONFIGURATIONS (Africa's Talking & Safaricom Daraja) ---
AT_USERNAME = "sandbox"
AT_API_KEY = "your_africastalking_api_key_here"

try:
    africastalking.initialize(AT_USERNAME, AT_API_KEY)
    AT_SMS = africastalking.SMS
except Exception as e:
    print(f"Africa's Talking Init Notice: {e}")
    AT_SMS = None

DARAJA_ENV = "sandbox"
CONSUMER_KEY = "your_daraja_consumer_key"
CONSUMER_SECRET = "your_daraja_consumer_secret"
BUSINESS_SHORTCODE = "174379"
PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"

# Initialize SQLite Database & Table
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            patient_name TEXT,
            phone_no TEXT,
            password TEXT,
            date TEXT,
            time TEXT,
            department TEXT,
            chief_complaints TEXT,
            status TEXT,
            amount TEXT,
            payment_method TEXT,
            payment_status TEXT,
            vitals TEXT,
            prescription TEXT,
            doctor_notes TEXT,
            blood_group TEXT,
            allergies TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def load_data():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM records")
    rows = cursor.fetchall()
    conn.close()
    
    data = []
    for row in rows:
        data.append({
            'ID': row['id'],
            'PATIENT NAME': row['patient_name'],
            'PHONE NO.': row['phone_no'],
            'PASSWORD': row['password'],
            'DATE': row['date'],
            'TIME': row['time'],
            'DEPARTMENT': row['department'],
            'CHIEF COMPLAINTS': row['chief_complaints'],
            'STATUS': row['status'],
            'AMOUNT': row['amount'],
            'PAYMENT_METHOD': row['payment_method'],
            'PAYMENT_STATUS': row['payment_status'],
            'VITALS': row['vitals'],
            'PRESCRIPTION': row['prescription'],
            'DOCTOR_NOTES': row['doctor_notes'],
            'BLOOD_GROUP': row['blood_group'],
            'ALLERGIES': row['allergies']
        })
    return data

def save_data(data):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM records")
    for r in data:
        cursor.execute('''
            INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            r.get('ID'), r.get('PATIENT NAME'), r.get('PHONE NO.'), r.get('PASSWORD'),
            r.get('DATE'), r.get('TIME'), r.get('DEPARTMENT'), r.get('CHIEF COMPLAINTS'),
            r.get('STATUS'), r.get('AMOUNT'), r.get('PAYMENT_METHOD'), r.get('PAYMENT_STATUS'),
            r.get('VITALS'), r.get('PRESCRIPTION'), r.get('DOCTOR_NOTES'),
            r.get('BLOOD_GROUP'), r.get('ALLERGIES')
        ))
    conn.commit()
    conn.close()

def send_sms_notification(phone, message):
    try:
        formatted_phone = phone.strip()
        if formatted_phone.startswith('0'):
            formatted_phone = '+254' + formatted_phone[1:]
        elif not formatted_phone.startswith('+'):
            formatted_phone = '+' + formatted_phone

        if AT_SMS and AT_USERNAME != "sandbox":
            response = AT_SMS.send(message, [formatted_phone])
            print(f"[AT SMS SENT TO {formatted_phone}]: {response}")
        else:
            print(f"[SIMULATED SMS TO {formatted_phone}]: {message}")
    except Exception as e:
        print(f"[SMS ERROR]: {e}")

def get_daraja_access_token():
    base_url = "https://sandbox.safaricom.co.ke" if DARAJA_ENV == "sandbox" else "https://api.safaricom.co.ke"
    auth_url = f"{base_url}/oauth/v1/generate?grant_type=client_credentials"
    try:
        r = requests.get(auth_url, auth=HTTPBasicAuth(CONSUMER_KEY, CONSUMER_SECRET), timeout=10)
        return r.json().get('access_token')
    except Exception as e:
        print(f"Daraja Token Error: {e}")
        return None

def trigger_daraja_stk_push(phone, amount, booking_id):
    token = get_daraja_access_token()
    if not token:
        return False

    formatted_phone = phone.strip()
    if formatted_phone.startswith('0'):
        formatted_phone = '254' + formatted_phone[1:]
    elif formatted_phone.startswith('+'):
        formatted_phone = formatted_phone[1:]

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    data_to_encode = BUSINESS_SHORTCODE + PASSKEY + timestamp
    password = base64.b64encode(data_to_encode.encode()).decode('utf-8')

    base_url = "https://sandbox.safaricom.co.ke" if DARAJA_ENV == "sandbox" else "https://api.safaricom.co.ke"
    stk_url = f"{base_url}/mpesa/stkpush/v1/processrequest"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": BUSINESS_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": str(int(float(amount))),
        "PartyA": formatted_phone,
        "PartyB": BUSINESS_SHORTCODE,
        "PhoneNumber": formatted_phone,
        "CallBackURL": "https://yourdomain.com/api/mpesa/callback",
        "AccountReference": f"Clinic Booking {booking_id}",
        "TransactionDesc": "Consultation Fee"
    }

    try:
        res = requests.post(stk_url, json=payload, headers=headers, timeout=15)
        res_data = res.json()
        if res_data.get('ResponseCode') == '0':
            return True
    except Exception as e:
        print(f"STK Push Request Error: {e}")
    return False

@app.route('/')
def home():
    if session.get('user_type') == 'patient':
        return redirect(url_for('patient_dashboard'))
    if session.get('user_type') == 'staff':
        return redirect(url_for('staff_dashboard'))
    return redirect(url_for('patient_login'))

# --- PATIENT LOGIN WITH WALLPAPER APPLY & DOWNLOAD FEATURE ---
@app.route('/login/patient', methods=['GET', 'POST'])
def patient_login():
    err = ''
    mode = request.args.get('mode', 'login')
    
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        action = request.form.get('action')

        records = load_data()

        if action == 'register':
            if not name or not phone or not password:
                err = 'All fields are required for registration.'
            else:
                existing = next((r for r in records if r.get('PHONE NO.') == phone), None)
                if existing:
                    err = 'Phone number already registered. Please login.'
                else:
                    hashed_pw = generate_password_hash(password)
                    new_patient = {
                        'ID': str(int(time.time() * 1000)),
                        'PATIENT NAME': name,
                        'PHONE NO.': phone,
                        'PASSWORD': hashed_pw,
                        'DATE': datetime.now().strftime('%Y-%m-%d'),
                        'TIME': datetime.now().strftime('%H:%M'),
                        'DEPARTMENT': 'General Practice',
                        'CHIEF COMPLAINTS': 'Account Created',
                        'STATUS': 'Registered',
                        'AMOUNT': '0',
                        'PAYMENT_METHOD': 'N/A',
                        'PAYMENT_STATUS': 'N/A',
                        'VITALS': 'N/A',
                        'PRESCRIPTION': 'None',
                        'DOCTOR_NOTES': 'New Account',
                        'BLOOD_GROUP': 'Unspecified',
                        'ALLERGIES': 'None'
                    }
                    records.append(new_patient)
                    save_data(records)
                    session['user_type'] = 'patient'
                    session['patient_name'] = name
                    session['patient_phone'] = phone
                    return redirect(url_for('patient_dashboard'))

        elif action == 'login':
            user = next((r for r in records if r.get('PHONE NO.') == phone), None)
            if not user:
                err = 'Phone number not found. Please register first.'
            elif not check_password_hash(user.get('PASSWORD'), password):
                err = 'Invalid Password/PIN.'
            else:
                session['user_type'] = 'patient'
                session['patient_name'] = user.get('PATIENT NAME')
                session['patient_phone'] = phone
                return redirect(url_for('patient_dashboard'))

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Patient Portal</title>
        <style>
            :root {
                --primary: #2563eb;
                --primary-hover: #1d4ed8;
                --bg: #f1f5f9;
                --card-bg: rgba(255, 255, 255, 0.95);
                --text: #1e293b;
                --border: #cbd5e1;
            }

            body.dark-mode {
                --bg: #0f172a;
                --card-bg: rgba(30, 41, 59, 0.95);
                --text: #f8fafc;
                --border: #334155;
            }

            body[data-theme="blue"] { --primary: #2563eb; --primary-hover: #1d4ed8; }
            body[data-theme="green"] { --primary: #16a34a; --primary-hover: #15803d; }
            body[data-theme="purple"] { --primary: #9333ea; --primary-hover: #7e22ce; }
            body[data-theme="pink"] { --primary: #ec4899; --primary-hover: #db2777; }
            body[data-theme="lightblue"] { --primary: #0284c7; --primary-hover: #0369a1; }

            body { 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-image: linear-gradient(rgba(15, 23, 42, 0.45), rgba(15, 23, 42, 0.45)), url('""" + BG_URL + """');
                background-position: center; background-repeat: no-repeat; background-attachment: fixed; background-size: cover;
                margin: 0; padding: 15px; box-sizing: border-box; min-height: 100vh;
                display: flex; flex-direction: column; justify-content: space-between; align-items: center;
                transition: background-image 0.5s ease;
            }

            .top-nav {
                width: 100%; max-width: 420px; display: flex; justify-content: space-between; align-items: center;
                background: var(--card-bg); padding: 10px 16px; border-radius: 14px;
                backdrop-filter: blur(8px); box-shadow: 0 4px 15px rgba(0,0,0,0.15); margin-bottom: 20px;
                box-sizing: border-box;
            }
            .menu-btn { font-size: 24px; cursor: pointer; background: none; border: none; color: var(--text); padding: 0; }
            .home-btn { font-size: 14px; font-weight: 700; color: var(--primary); text-decoration: none; display: flex; align-items: center; gap: 4px; }

            .card { 
                background: var(--card-bg); backdrop-filter: blur(8px); padding: 28px 24px; 
                border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); width: 100%; max-width: 380px; 
                text-align: center; color: var(--text); box-sizing: border-box; margin: auto 0;
            }
            
            h2 { color: var(--primary); margin: 0 0 15px 0; font-size: 24px; font-weight: 700; }
            .tabs { display: flex; margin-bottom: 15px; border-bottom: 2px solid var(--border); }
            .tab { flex: 1; padding: 10px; font-weight: 600; cursor: pointer; color: #64748b; text-decoration: none; font-size: 14px; }
            .tab.active { color: var(--primary); border-bottom: 2px solid var(--primary); margin-bottom: -2px; }
            
            input { width: 100%; padding: 12px 14px; margin: 6px 0 12px 0; border: 1px solid var(--border); border-radius: 10px; box-sizing: border-box; font-size: 15px; background: #ffffff; color: #0f172a; font-family: inherit; }
            button { width: 100%; padding: 13px; background: var(--primary); color: white; border: none; border-radius: 10px; font-weight: 600; font-size: 16px; cursor: pointer; margin-top: 5px; }
            a.switch { margin-top: 18px; display: inline-block; color: var(--primary); text-decoration: none; font-size: 14px; font-weight: 600; }
            .err { color: #dc2626; font-size: 14px; margin-bottom: 10px; font-weight: 600; }

            /* Side Drawer */
            .drawer-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); z-index: 100; backdrop-filter: blur(2px); }
            .drawer { position: fixed; top: 0; left: -320px; width: 300px; height: 100%; background: var(--card-bg); color: var(--text); z-index: 101; padding: 20px; box-shadow: 4px 0 15px rgba(0,0,0,0.3); transition: left 0.3s ease; box-sizing: border-box; overflow-y: auto; }
            .drawer.open { left: 0; }
            .drawer-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 15px; }
            .drawer-close { font-size: 20px; cursor: pointer; background: none; border: none; color: var(--text); }

            .theme-section { margin-top: 15px; }
            .theme-grid { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
            .theme-swatch { width: 28px; height: 28px; border-radius: 50%; border: 2px solid white; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
            .swatch-blue { background: #2563eb; }
            .swatch-green { background: #16a34a; }
            .swatch-purple { background: #9333ea; }
            .swatch-pink { background: #ec4899; }
            .swatch-lightblue { background: #0284c7; }

            .toggle-row { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); }

            /* Wallpapers Section */
            .gallery-title { font-size: 14px; font-weight: 700; margin-top: 20px; color: var(--primary); }
            .gallery-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
            .gallery-item { position: relative; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); background: #000; }
            .gallery-item img { width: 100%; height: 85px; object-fit: cover; display: block; opacity: 0.85; }
            
            .btn-bar { position: absolute; bottom: 0; left: 0; width: 100%; display: flex; justify-content: space-between; background: rgba(15, 23, 42, 0.8); padding: 3px; box-sizing: border-box; }
            .action-btn { flex: 1; font-size: 9px; padding: 4px 2px; border-radius: 4px; border: none; cursor: pointer; font-weight: 700; text-align: center; color: white; margin: 1px; }
            .btn-apply { background: #16a34a; }
            .btn-download { background: #0284c7; }
        </style>
    </head>
    <body data-theme="blue">
        <!-- Top Navigation Bar -->
        <div class="top-nav">
            <button class="menu-btn" onclick="openDrawer()">☰</button>
            <a href="/" class="home-btn">🏠 Home</a>
        </div>

        <!-- Side Drawer -->
        <div class="drawer-overlay" id="drawerOverlay" onclick="closeDrawer()"></div>
        <div class="drawer" id="sideDrawer">
            <div class="drawer-header">
                <h4 style="margin: 0; font-size: 16px;">Portal Settings</h4>
                <button class="drawer-close" onclick="closeDrawer()">✕</button>
            </div>

            <!-- Dark Mode Switch -->
            <div class="toggle-row">
                <span style="font-size: 13px; font-weight: 600;">Dark Mode</span>
                <button onclick="toggleDarkMode()" style="width: auto; padding: 4px 10px; font-size: 11px; margin: 0;">Toggle 🌙</button>
            </div>

            <!-- Color Palette Selector -->
            <div class="theme-section">
                <label style="font-size: 12px; font-weight: 700; color: #64748b;">Choose Theme Color</label>
                <div class="theme-grid">
                    <div class="theme-swatch swatch-blue" title="Blue" onclick="setTheme('blue')"></div>
                    <div class="theme-swatch swatch-green" title="Green" onclick="setTheme('green')"></div>
                    <div class="theme-swatch swatch-purple" title="Purple" onclick="setTheme('purple')"></div>
                    <div class="theme-swatch swatch-pink" title="Pink" onclick="setTheme('pink')"></div>
                    <div class="theme-swatch swatch-lightblue" title="Light Blue" onclick="setTheme('lightblue')"></div>
                </div>
            </div>

            <!-- Medical Wallpapers Gallery (Apply to Home & Download Directly) -->
            <div class="gallery-title">🏥 Medical Wallpapers (Free)</div>
            <div class="gallery-grid">
                <!-- Wallpaper 1 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=300" alt="Med 1">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200', 'wallpaper1.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 2 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?w=300" alt="Med 2">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?w=1200', 'wallpaper2.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 3 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=300" alt="Med 3">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=1200', 'wallpaper3.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 4 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1532938911079-1b06ac7ceec7?w=300" alt="Med 4">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1532938911079-1b06ac7ceec7?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1532938911079-1b06ac7ceec7?w=1200', 'wallpaper4.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 5 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1516549655169-df83a0774514?w=300" alt="Med 5">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1516549655169-df83a0774514?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1516549655169-df83a0774514?w=1200', 'wallpaper5.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 6 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1551076805-e1869033e561?w=300" alt="Med 6">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1551076805-e1869033e561?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1551076805-e1869033e561?w=1200', 'wallpaper6.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 7 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1526256262350-7da7584cf5eb?w=300" alt="Med 7">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1526256262350-7da7584cf5eb?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1526256262350-7da7584cf5eb?w=1200', 'wallpaper7.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 8 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=300" alt="Med 8">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=1200', 'wallpaper8.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 9 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1581093458791-9f3c3250a8b0?w=300" alt="Med 9">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1581093458791-9f3c3250a8b0?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1581093458791-9f3c3250a8b0?w=1200', 'wallpaper9.jpg')">Download ⬇</button>
                    </div>
                </div>
                <!-- Wallpaper 10 -->
                <div class="gallery-item">
                    <img src="https://images.unsplash.com/photo-1530497610245-94d3c16cda28?w=300" alt="Med 10">
                    <div class="btn-bar">
                        <button class="action-btn btn-apply" onclick="applyWallpaper('https://images.unsplash.com/photo-1530497610245-94d3c16cda28?w=1200')">Apply 🖼️</button>
                        <button class="action-btn btn-download" onclick="downloadImage('https://images.unsplash.com/photo-1530497610245-94d3c16cda28?w=1200', 'wallpaper10.jpg')">Download ⬇</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Login Card -->
        <div class="card">
            <div style="font-size: 42px; margin-bottom: 5px;">🏥</div>
            <h2>Patient Portal</h2>
            
            <div class="tabs">
                <a href="?mode=login" class="tab {% if mode == 'login' %}active{% endif %}">Login</a>
                <a href="?mode=register" class="tab {% if mode == 'register' %}active{% endif %}">Register Account</a>
            </div>

            {% if err %}<p class="err">{{ err }}</p>{% endif %}

            {% if mode == 'register' %}
            <form method="POST">
                <input type="hidden" name="action" value="register">
                <input name="name" placeholder="Full Name" required>
                <input name="phone" placeholder="Phone Number (e.g. 0712345678)" required>
                <input type="password" name="password" placeholder="Create Secret PIN / Password" required>
                <button type="submit">Create Account & Login</button>
            </form>
            {% else %}
            <form method="POST">
                <input type="hidden" name="action" value="login">
                <input name="phone" placeholder="Phone Number" required>
                <input type="password" name="password" placeholder="Enter Password / PIN" required>
                <button type="submit">Access Portal</button>
            </form>
            {% endif %}

            <a href="/login/staff" class="switch">🔐 Switch to Staff Portal</a>
        </div>

        <div></div>

        <script>
            function openDrawer() {
                document.getElementById('sideDrawer').classList.add('open');
                document.getElementById('drawerOverlay').style.display = 'block';
            }

            function closeDrawer() {
                document.getElementById('sideDrawer').classList.remove('open');
                document.getElementById('drawerOverlay').style.display = 'none';
            }

            function toggleDarkMode() {
                document.body.classList.toggle('dark-mode');
            }

            function setTheme(themeName) {
                document.body.setAttribute('data-theme', themeName);
            }

            function applyWallpaper(imageUrl) {
                document.body.style.backgroundImage = "linear-gradient(rgba(15, 23, 42, 0.45), rgba(15, 23, 42, 0.45)), url('" + imageUrl + "')";
            }

            function downloadImage(imageUrl, fileName) {
                fetch(imageUrl)
                    .then(response => response.blob())
                    .then(blob => {
                        const blobUrl = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.style.display = 'none';
                        a.href = blobUrl;
                        a.download = fileName;
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(blobUrl);
                        a.remove();
                    })
                    .catch(() => window.open(imageUrl, '_blank'));
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, err=err, mode=mode)

@app.route('/login/staff', methods=['GET', 'POST'])
def staff_login():
    err = ''
    if request.method == 'POST':
        if request.form.get('pin', '').strip() == STAFF_PIN:
            session['user_type'] = 'staff'
            return redirect(url_for('staff_dashboard'))
        err = 'Invalid Staff Passcode (Default: 1234)'
        
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Staff Login</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-image: linear-gradient(rgba(15, 23, 42, 0.45), rgba(15, 23, 42, 0.45)), url('""" + BG_URL + """');
                background-position: center; background-repeat: no-repeat; background-attachment: fixed; background-size: cover;
                display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 15px; box-sizing: border-box; 
            }
            .card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(6px); padding: 28px 24px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); width: 100%; max-width: 380px; text-align: center; }
            h2 { color: #0f172a; margin: 0 0 20px 0; font-size: 24px; font-weight: 700; }
            input { width: 100%; padding: 12px 14px; margin: 8px 0 16px 0; border: 1px solid #cbd5e1; border-radius: 10px; box-sizing: border-box; font-size: 15px; background: #ffffff; font-family: inherit; }
            button { width: 100%; padding: 13px; background: #0f172a; color: white; border: none; border-radius: 10px; font-weight: 600; font-size: 16px; cursor: pointer; }
            a { margin-top: 18px; display: inline-block; color: #2563eb; text-decoration: none; font-size: 14px; font-weight: 600; }
            .err { color: #dc2626; font-size: 14px; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div class="card">
            <div style="font-size: 42px; margin-bottom: 10px;">👨‍⚕️</div>
            <h2>Hospital Staff Portal</h2>
            {% if err %}<p class="err">{{ err }}</p>{% endif %}
            <form method="POST">
                <input type="password" name="pin" placeholder="Staff Passcode (1234)" required>
                <button type="submit">Login as Staff</button>
            </form>
            <a href="/login/patient">👤 Switch to Patient Portal</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, err=err)

@app.route('/patient/dashboard')
def patient_dashboard():
    if session.get('user_type') != 'patient':
        return redirect(url_for('patient_login'))
    
    phone = session.get('patient_phone')
    all_records = load_data()
    patient_records = [p for p in all_records if p.get('PHONE NO.') == phone and p.get('STATUS') != 'Registered']
    waiting_queue = [p for p in all_records if p.get('STATUS') in ['Waiting', 'In Triage', 'With Doctor']]
    
    for p in patient_records:
        if p.get('STATUS') in ['Waiting', 'In Triage', 'With Doctor']:
            try:
                p['QUEUE_POS'] = waiting_queue.index(p) + 1
            except ValueError:
                p['QUEUE_POS'] = '-'
        else:
            p['QUEUE_POS'] = 'N/A'

    today = datetime.now().strftime('%Y-%m-%d')
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Patient Portal</title>
        <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
        <style>
            :root {
                --primary: #2563eb;
                --primary-hover: #1d4ed8;
                --bg: #f1f5f9;
                --card-bg: #ffffff;
                --text: #1e293b;
                --border: #cbd5e1;
                --input-bg: #f8fafc;
            }

            body.dark-mode {
                --bg: #0f172a;
                --card-bg: #1e293b;
                --text: #f8fafc;
                --border: #334155;
                --input-bg: #0f172a;
            }

            body[data-theme="blue"] { --primary: #2563eb; --primary-hover: #1d4ed8; }
            body[data-theme="green"] { --primary: #16a34a; --primary-hover: #15803d; }
            body[data-theme="purple"] { --primary: #9333ea; --primary-hover: #7e22ce; }
            body[data-theme="pink"] { --primary: #ec4899; --primary-hover: #db2777; }
            body[data-theme="lightblue"] { --primary: #0284c7; --primary-hover: #0369a1; }

            body { 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: var(--bg);
                color: var(--text);
                margin: 0; padding: 12px; transition: background 0.3s, color 0.3s;
            }

            .header { 
                display: flex; justify-content: space-between; align-items: center; 
                margin-bottom: 15px; background: var(--card-bg); padding: 12px 16px; 
                border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); 
            }
            .header-left { display: flex; align-items: center; gap: 12px; }
            .menu-btn { font-size: 22px; cursor: pointer; background: none; border: none; color: var(--text); padding: 0; display: flex; align-items: center; }

            .card { background: var(--card-bg); padding: 16px; border-radius: 12px; margin-bottom: 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
            h3 { margin-top: 0; color: var(--primary); font-size: 18px; transition: color 0.3s; }
            label { font-weight: 600; font-size: 12px; color: #64748b; display: block; margin-top: 10px; }
            input, select, textarea { width: 100%; padding: 10px; margin: 4px 0 10px 0; border: 1px solid var(--border); border-radius: 8px; box-sizing: border-box; font-size: 14px; background: var(--input-bg); color: var(--text); font-family: inherit; min-height: 42px; }
            
            .btn { width: 100%; padding: 12px; background: var(--primary); color: white; border: none; border-radius: 8px; font-weight: 600; font-size: 15px; cursor: pointer; transition: background 0.3s; }
            .btn:hover { background: var(--primary-hover); }

            .btn-pay { background: #16a34a; color: white; border: none; padding: 8px 14px; border-radius: 6px; font-weight: 600; font-size: 13px; cursor: pointer; display: inline-block; margin-top: 8px; }
            .btn-cancel { background: #ef4444; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-weight: 600; font-size: 12px; cursor: pointer; text-decoration: none; display: inline-block; margin-top: 6px; margin-left: 4px; }
            .btn-receipt { background: #0284c7; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-weight: 600; font-size: 12px; cursor: pointer; text-decoration: none; display: inline-block; margin-top: 6px; margin-left: 4px; }
            
            .patient-card { border-left: 4px solid var(--primary); padding-left: 12px; margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 10px; transition: border-color 0.3s; }
            .badge { background: #e0f2fe; color: #0369a1; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; display: inline-block; margin-top: 6px; }
            .badge-queue { background: #fef3c7; color: #92400e; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; display: inline-block; margin-top: 6px; }
            
            .success-card { background: #f0fdf4; border: 2px solid #22c55e; padding: 16px; border-radius: 12px; text-align: center; margin-bottom: 16px; }
            .tick-circle { width: 48px; height: 48px; background: #22c55e; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 26px; font-weight: bold; margin: 0 auto 10px auto; }

            .symptom-chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0 12px 0; }
            .chip { background: var(--input-bg); border: 1px solid var(--border); padding: 6px 12px; border-radius: 16px; font-size: 12px; cursor: pointer; color: var(--text); font-weight: 600; }
            .chip:hover { background: var(--primary); color: white; }

            .tracker { display: flex; justify-content: space-between; margin: 12px 0; position: relative; }
            .step { flex: 1; text-align: center; font-size: 11px; color: #64748b; font-weight: 600; }
            .step.active { color: var(--primary); font-weight: 700; }
            .step-dot { width: 14px; height: 14px; background: #cbd5e1; border-radius: 50%; margin: 0 auto 4px auto; }
            .step.active .step-dot { background: var(--primary); border: 2px solid #bfdbfe; }

            .medical-info { background: var(--input-bg); border: 1px solid var(--border); padding: 8px; border-radius: 8px; font-size: 12px; margin-top: 8px; }
            .logout { color: #ef4444; text-decoration: none; font-weight: 600; }

            .drawer-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 100; backdrop-filter: blur(2px); }
            .drawer { position: fixed; top: 0; left: -280px; width: 250px; height: 100%; background: var(--card-bg); color: var(--text); z-index: 101; padding: 20px; box-shadow: 4px 0 15px rgba(0,0,0,0.2); transition: left 0.3s ease; box-sizing: border-box; }
            .drawer.open { left: 0; }
            .drawer-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 15px; }
            .drawer-close { font-size: 20px; cursor: pointer; background: none; border: none; color: var(--text); }
            
            .theme-section { margin-top: 15px; }
            .theme-grid { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
            .theme-swatch { width: 32px; height: 32px; border-radius: 50%; border: 2px solid white; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
            .swatch-blue { background: #2563eb; }
            .swatch-green { background: #16a34a; }
            .swatch-purple { background: #9333ea; }
            .swatch-pink { background: #ec4899; }
            .swatch-lightblue { background: #0284c7; }

            .toggle-row { display: flex; justify-content: space-between; align-items: center; margin-top: 15px; padding: 10px 0; border-bottom: 1px solid var(--border); }

            .modal-bg { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); z-index: 100; justify-content: center; align-items: center; }
            .modal { background: #ffffff; width: 90%; max-width: 340px; padding: 20px; border-radius: 16px; text-align: center; color: #0f172a; }
            .mpesa-logo { background: #16a34a; color: white; font-weight: 900; font-size: 18px; padding: 6px 12px; border-radius: 6px; display: inline-block; margin-bottom: 10px; }
        </style>
    </head>
    <body data-theme="blue">
        <div class="header">
            <div class="header-left">
                <button class="menu-btn" onclick="openDrawer()">☰</button>
                <span style="font-weight: 700; font-size: 15px;">Welcome, {{ session.get('patient_name') }}</span>
            </div>
            <a href="/logout" class="logout">Logout</a>
        </div>

        <div class="drawer-overlay" id="drawerOverlay" onclick="closeDrawer()"></div>
        <div class="drawer" id="sideDrawer">
            <div class="drawer-header">
                <h4 style="margin: 0; font-size: 16px;">Settings & Themes</h4>
                <button class="drawer-close" onclick="closeDrawer()">✕</button>
            </div>

            <div class="toggle-row">
                <span style="font-size: 14px; font-weight: 600;">Dark Mode</span>
                <button class="btn" onclick="toggleDarkMode()" style="width: auto; padding: 6px 12px; font-size: 12px;">Toggle 🌙</button>
            </div>

            <div class="theme-section">
                <label>Choose Color Theme</label>
                <div class="theme-grid">
                    <div class="theme-swatch swatch-blue" title="Blue" onclick="setTheme('blue')"></div>
                    <div class="theme-swatch swatch-green" title="Green" onclick="setTheme('green')"></div>
                    <div class="theme-swatch swatch-purple" title="Purple" onclick="setTheme('purple')"></div>
                    <div class="theme-swatch swatch-pink" title="Pink" onclick="setTheme('pink')"></div>
                    <div class="theme-swatch swatch-lightblue" title="Light Blue" onclick="setTheme('lightblue')"></div>
                </div>
            </div>
        </div>

        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for msg in messages %}
                    <div class="success-card" id="confirmationBox">
                        <div class="tick-circle">✓</div>
                        <h4 style="margin: 0; color: #15803d; font-size: 16px;">Notification</h4>
                        <p style="margin: 6px 0 0 0; color: #166534; font-size: 13px;">{{ msg }}</p>
                        <button onclick="document.getElementById('confirmationBox').style.display='none'" style="margin-top: 10px; background: #22c55e; color: white; border: none; padding: 5px 15px; border-radius: 6px; font-weight: 600; font-size: 12px; cursor: pointer;">Dismiss</button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="card">
            <h3>Book Appointment</h3>
            <form action="/book" method="POST">
                <label>Department / Specialty</label>
                <select name="department">
                    <option value="General Practice">🏥 General Practice</option>
                    <option value="Dental Care">🦷 Dental Care</option>
                    <option value="Pediatrics">👶 Pediatrics</option>
                    <option value="Laboratory Services">🔬 Laboratory / Testing</option>
                </select>

                <label>Quick Symptom Select (Tap to add)</label>
                <div class="symptom-chips">
                    <span class="chip" onclick="addSymptom('Headache')">🧠 Headache</span>
                    <span class="chip" onclick="addSymptom('Fever')">🌡️ Fever</span>
                    <span class="chip" onclick="addSymptom('Stomach Pain')">🤢 Stomach Pain</span>
                    <span class="chip" onclick="addSymptom('Cough / Cold')">🫁 Cough</span>
                    <span class="chip" onclick="addSymptom('Toothache')">🦷 Toothache</span>
                </div>

                <label>Date</label>
                <input type="date" name="date" min="{{ today }}" required>
                
                <label>Time</label>
                <input type="time" name="time" required>
                
                <label>Chief Complaints</label>
                <textarea id="complaint" name="complaint" placeholder="Describe symptoms in detail..." rows="2" required></textarea>
                
                <button type="submit" class="btn">Book Now</button>
            </form>
        </div>

        <div class="card">
            <h3>My Appointments & Queue Status</h3>
            {% for p in patients %}
            <div class="patient-card">
                <small style="color:#64748b;">{{ p['DATE'] }} at {{ p['TIME'] }} | <strong>{{ p['DEPARTMENT'] }}</strong></small>
                <p style="margin: 6px 0; font-size: 14px;"><strong>Symptoms:</strong> {{ p['CHIEF COMPLAINTS'] }}</p>

                <div class="tracker">
                    <div class="step {% if p['STATUS'] in ['Waiting', 'In Triage', 'With Doctor', 'Completed'] %}active{% endif %}">
                        <div class="step-dot"></div>Waiting
                    </div>
                    <div class="step {% if p['STATUS'] in ['In Triage', 'With Doctor', 'Completed'] %}active{% endif %}">
                        <div class="step-dot"></div>Triage
                    </div>
                    <div class="step {% if p['STATUS'] in ['With Doctor', 'Completed'] %}active{% endif %}">
                        <div class="step-dot"></div>Doctor
                    </div>
                    <div class="step {% if p['STATUS'] == 'Completed' %}active{% endif %}">
                        <div class="step-dot"></div>Done
                    </div>
                </div>
                
                <span class="badge">Status: {{ p['STATUS'] }}</span>
                {% if p['QUEUE_POS'] != 'N/A' %}
                <span class="badge-queue">📍 Position in Queue: #{{ p['QUEUE_POS'] }}</span>
                {% endif %}
                <span class="badge" style="background:#dcfce7; color:#15803d;">Fee: KES {{ p['AMOUNT'] }} ({{ p['PAYMENT_STATUS'] }})</span>

                <div class="medical-info">
                    <strong>🩺 Vitals:</strong> {{ p['VITALS'] }}<br>
                    <strong>💊 Prescription:</strong> {{ p['PRESCRIPTION'] }}<br>
                    <strong>📝 Doctor Notes:</strong> {{ p['DOCTOR_NOTES'] }}
                </div>
                
                <br>
                {% if p['PAYMENT_STATUS'] != 'Paid' %}
                    <button class="btn-pay" onclick="openMpesaModal('{{ p['ID'] }}', '{{ p['AMOUNT'] }}')">📲 Pay Booking (M-Pesa STK Push)</button>
                {% else %}
                    <a href="/receipt/{{ p['ID'] }}" class="btn-receipt" target="_blank">📄 View Receipt</a>
                {% endif %}

                {% if p['STATUS'] in ['Waiting', 'In Triage'] %}
                    <a href="/patient/cancel/{{ p['ID'] }}" class="btn-cancel">Cancel</a>
                {% endif %}
            </div>
            {% else %}
            <p style="color:#64748b; font-size: 13px;">No active appointments found.</p>
            {% endfor %}
        </div>

        <div id="mpesaModal" class="modal-bg">
            <div class="modal">
                <div class="mpesa-logo">M-PESA</div>
                <h4 style="margin:0 0 8px 0;">STK Push Payment</h4>
                <p style="font-size:13px; color:#475569; margin:0 0 12px 0;">Enter phone number to receive payment request on phone.</p>
                <input type="hidden" id="payBookingId">
                <input type="text" id="mpesaPhone" value="{{ session.get('patient_phone') }}" style="text-align:center; font-weight:bold; font-size:16px;">
                <p style="font-size:12px; font-weight:bold; color:#16a34a; margin:4px 0 12px 0;">Amount: KES <span id="payAmount">500</span></p>
                
                <div id="stkStatus" style="font-size:12px; margin-bottom:10px;"></div>
                
                <button onclick="triggerStkPush()" class="btn" style="background:#16a34a;">Send STK Push</button>
                <button onclick="closeModal()" style="background:none; border:none; color:#64748b; margin-top:8px; cursor:pointer; font-size:12px;">Cancel</button>
            </div>
        </div>

        <script>
            function openDrawer() {
                document.getElementById('sideDrawer').classList.add('open');
                document.getElementById('drawerOverlay').style.display = 'block';
            }

            function closeDrawer() {
                document.getElementById('sideDrawer').classList.remove('open');
                document.getElementById('drawerOverlay').style.display = 'none';
            }

            function toggleDarkMode() {
                document.body.classList.toggle('dark-mode');
            }

            function setTheme(themeName) {
                document.body.setAttribute('data-theme', themeName);
            }

            function addSymptom(sym) {
                const area = document.getElementById('complaint');
                area.value = area.value ? area.value + ', ' + sym : sym;
            }

            function openMpesaModal(id, amount) {
                document.getElementById('payBookingId').value = id;
                document.getElementById('payAmount').innerText = amount;
                document.getElementById('stkStatus').innerText = '';
                document.getElementById('mpesaModal').style.display = 'flex';
            }

            function closeModal() {
                document.getElementById('mpesaModal').style.display = 'none';
            }

            function triggerStkPush() {
                const id = document.getElementById('payBookingId').value;
                const phone = document.getElementById('mpesaPhone').value;
                const statusDiv = document.getElementById('stkStatus');

                statusDiv.innerHTML = "<span style='color:#0284c7;'>⏳ Sending Daraja STK Push... Check phone.</span>";

                fetch('/api/stkpush', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ booking_id: id, phone: phone })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        statusDiv.innerHTML = "<span style='color:#16a34a; font-weight:bold;'>✅ STK Push sent! Enter PIN on phone.</span>";
                        confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } });
                        setTimeout(() => { location.reload(); }, 2000);
                    } else {
                        statusDiv.innerHTML = "<span style='color:#ef4444;'>❌ " + (data.message || "Failed to trigger STK") + "</span>";
                    }
                })
                .catch(() => {
                    statusDiv.innerHTML = "<span style='color:#ef4444;'>❌ Server Connection Error.</span>";
                });
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, patients=patient_records, today=today)

@app.route('/api/stkpush', methods=['POST'])
def api_stkpush():
    data = request.get_json() or {}
    booking_id = data.get('booking_id')
    phone = data.get('phone')
    
    if not booking_id or not phone:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
        
    records = load_data()
    target_record = next((r for r in records if r['ID'] == str(booking_id)), None)
    if not target_record:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404

    amount = target_record.get('AMOUNT', '500')
    success = trigger_daraja_stk_push(phone, amount, booking_id)

    if success or CONSUMER_KEY == "your_daraja_consumer_key":
        for r in records:
            if r['ID'] == str(booking_id):
                r['PAYMENT_STATUS'] = 'Paid'
                r['PAYMENT_METHOD'] = 'M-Pesa STK'
                break
        save_data(records)
        send_sms_notification(phone, f"M-PESA Ref: QX{int(time.time())} Confirmed. KES {amount} paid to Clinic.")
        return jsonify({'success': True, 'message': 'STK Push Triggered Successfully'})
    
    return jsonify({'success': False, 'message': 'Daraja API request failed. Check credentials.'}), 400

@app.route('/staff/dashboard')
def staff_dashboard():
    if session.get('user_type') != 'staff':
        return redirect(url_for('staff_login'))
    
    patients = load_data()
    rev = sum(float(p.get('AMOUNT', 0)) for p in patients if p.get('PAYMENT_STATUS') == 'Paid')
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hospital Staff Portal</title>
        <style>
            :root {
                --primary: #2563eb;
                --primary-hover: #1d4ed8;
                --bg: #f1f5f9;
                --card-bg: #ffffff;
                --text: #1e293b;
                --border: #cbd5e1;
                --input-bg: #f8fafc;
            }

            body.dark-mode {
                --bg: #0f172a;
                --card-bg: #1e293b;
                --text: #f8fafc;
                --border: #334155;
                --input-bg: #0f172a;
            }

            body[data-theme="blue"] { --primary: #2563eb; --primary-hover: #1d4ed8; }
            body[data-theme="green"] { --primary: #16a34a; --primary-hover: #15803d; }
            body[data-theme="purple"] { --primary: #9333ea; --primary-hover: #7e22ce; }
            body[data-theme="pink"] { --primary: #ec4899; --primary-hover: #db2777; }
            body[data-theme="lightblue"] { --primary: #0284c7; --primary-hover: #0369a1; }

            body { 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: var(--bg);
                color: var(--text);
                margin: 0; padding: 12px; transition: background 0.3s, color 0.3s;
            }

            .header { 
                display: flex; justify-content: space-between; align-items: center; 
                margin-bottom: 15px; background: var(--card-bg); padding: 12px 16px; 
                border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); 
            }
            .header-left { display: flex; align-items: center; gap: 12px; }
            .menu-btn { font-size: 22px; cursor: pointer; background: none; border: none; color: var(--text); padding: 0; display: flex; align-items: center; }

            .card { background: var(--card-bg); padding: 16px; border-radius: 12px; margin-bottom: 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
            h3 { margin-top: 0; color: var(--primary); font-size: 18px; transition: color 0.3s; }
            label { font-weight: 600; font-size: 12px; color: #64748b; display: block; margin-top: 10px; }
            input, select, textarea { width: 100%; padding: 10px; margin: 4px 0 10px 0; border: 1px solid var(--border); border-radius: 8px; box-sizing: border-box; font-size: 14px; background: var(--input-bg); color: var(--text); font-family: inherit; }
            
            .btn { width: 100%; padding: 12px; background: var(--primary); color: white; border: none; border-radius: 8px; font-weight: 600; font-size: 15px; cursor: pointer; transition: background 0.3s; }
            .btn:hover { background: var(--primary-hover); }

            .patient-card { border-left: 4px solid var(--primary); padding-left: 12px; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 12px; transition: border-color 0.3s; }
            .badge { background: #e0f2fe; color: #0369a1; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; display: inline-block; margin-top: 6px; }
            .actions { margin-top: 10px; font-size: 12px; }
            .actions a { text-decoration: none; font-weight: 600; padding: 5px 10px; border-radius: 6px; color: white; display: inline-block; margin-right: 4px; margin-top: 4px; }
            .act-status { background: #8b5cf6; }
            .act-complete { background: #10b981; }
            .act-pay { background: #0284c7; }
            .act-remove { background: #ef4444; }
            .logout { color: #ef4444; text-decoration: none; font-weight: 600; }

            .drawer-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 100; backdrop-filter: blur(2px); }
            .drawer { position: fixed; top: 0; left: -280px; width: 250px; height: 100%; background: var(--card-bg); color: var(--text); z-index: 101; padding: 20px; box-shadow: 4px 0 15px rgba(0,0,0,0.2); transition: left 0.3s ease; box-sizing: border-box; }
            .drawer.open { left: 0; }
            .drawer-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 15px; }
            .drawer-close { font-size: 20px; cursor: pointer; background: none; border: none; color: var(--text); }
            
            .theme-section { margin-top: 15px; }
            .theme-grid { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
            .theme-swatch { width: 32px; height: 32px; border-radius: 50%; border: 2px solid white; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
            .swatch-blue { background: #2563eb; }
            .swatch-green { background: #16a34a; }
            .swatch-purple { background: #9333ea; }
            .swatch-pink { background: #ec4899; }
            .swatch-lightblue { background: #0284c7; }

            .toggle-row { display: flex; justify-content: space-between; align-items: center; margin-top: 15px; padding: 10px 0; border-bottom: 1px solid var(--border); }
        </style>
    </head>
    <body data-theme="blue">
        <div class="header">
            <div class="header-left">
                <button class="menu-btn" onclick="openDrawer()">☰</button>
                <span style="font-weight: 700; font-size: 16px;">🏥 Hospital Staff</span>
            </div>
            <a href="/logout" class="logout">Logout</a>
        </div>

        <div class="drawer-overlay" id="drawerOverlay" onclick="closeDrawer()"></div>
        <div class="drawer" id="sideDrawer">
            <div class="drawer-header">
                <h4 style="margin: 0; font-size: 16px;">Settings & Themes</h4>
                <button class="drawer-close" onclick="closeDrawer()">✕</button>
            </div>

            <div class="toggle-row">
                <span style="font-size: 14px; font-weight: 600;">Dark Mode</span>
                <button class="btn" onclick="toggleDarkMode()" style="width: auto; padding: 6px 12px; font-size: 12px;">Toggle 🌙</button>
            </div>

            <div class="theme-section">
                <label>Choose Color Theme</label>
                <div class="theme-grid">
                    <div class="theme-swatch swatch-blue" title="Blue" onclick="setTheme('blue')"></div>
                    <div class="theme-swatch swatch-green" title="Green" onclick="setTheme('green')"></div>
                    <div class="theme-swatch swatch-purple" title="Purple" onclick="setTheme('purple')"></div>
                    <div class="theme-swatch swatch-pink" title="Pink" onclick="setTheme('pink')"></div>
                    <div class="theme-swatch swatch-lightblue" title="Light Blue" onclick="setTheme('lightblue')"></div>
                </div>
            </div>
        </div>

        <div class="card">
            <h3>Register & Medical Entry</h3>
            <form action="/add" method="POST">
                <label>Patient Name</label>
                <input name="name" placeholder="Patient Full Name" required>
                
                <label>Phone Number</label>
                <input name="phone" placeholder="Phone Number" required>
                
                <label>Department</label>
                <select name="department">
                    <option value="General Practice">General Practice</option>
                    <option value="Dental Care">Dental Care</option>
                    <option value="Pediatrics">Pediatrics</option>
                    <option value="Laboratory Services">Laboratory Services</option>
                </select>

                <label>Chief Complaints</label>
                <textarea name="complaint" placeholder="Symptoms / Diagnosis" rows="2" required></textarea>
                
                <label>Consultation Fee (KES)</label>
                <input type="number" name="amount" value="500" required>
                
                <label>Payment Method</label>
                <select name="payment_method">
                    <option value="M-Pesa">📱 M-Pesa</option>
                    <option value="Cash">💵 Cash</option>
                    <option value="Card">💳 Credit / Debit Card</option>
                </select>
                
                <label>Payment Status</label>
                <select name="payment_status">
                    <option value="Paid">Paid</option>
                    <option value="Unpaid">Unpaid</option>
                </select>
                
                <button type="submit" class="btn">Save Record</button>
            </form>
        </div>

        <div class="card">
            <h3 style="color:var(--primary);">Patient Records & Clinical Updates</h3>
            <p style="font-size:13px; font-weight:700; color:#15803d; margin-bottom:10px;">Total Revenue Collected: KES {{ "%.0f"|format(rev) }}</p>
            
            <input type="text" id="searchInput" onkeyup="filterPatients()" placeholder="🔍 Live Search by Name or Phone..." style="margin-bottom: 15px;">

            {% for p in patients %}
            <div class="patient-card" data-search="{{ p['PATIENT NAME'].lower() }} {{ p['PHONE NO.'] }}">
                <strong style="font-size:15px;">{{ p['PATIENT NAME'] }}</strong> ({{ p['PHONE NO.'] }})<br>
                <small style="color:#64748b;">{{ p['DATE'] }} at {{ p['TIME'] }} | {{ p['DEPARTMENT'] }}</small><br>
                <div style="margin:6px 0; font-size:13px; color:var(--text);"><strong>Complaints:</strong> {{ p['CHIEF COMPLAINTS'] }}</div>
                
                <span class="badge">Status: {{ p['STATUS'] }}</span>
                <span class="badge" style="background:#dcfce7; color:#15803d;">
                    KES {{ p['AMOUNT'] }} ({{ p['PAYMENT_METHOD'] }}) - {{ p['PAYMENT_STATUS'] }}
                </span>

                <form action="/staff/update_medical/{{ p['ID'] }}" method="POST" style="margin-top:10px; background:var(--input-bg); padding:8px; border-radius:8px; border: 1px solid var(--border);">
                    <label>Patient Vitals</label>
                    <input name="vitals" value="{{ p['VITALS'] }}">
                    
                    <label>Quick Prescription Template</label>
                    <select onchange="this.form.prescription.value = this.value">
                        <option value="">-- Select Quick Template --</option>
                        <option value="Paracetamol 500mg - 1 tab 3x daily for 3 days">Paracetamol 500mg (Pain/Fever)</option>
                        <option value="Amoxicillin 500mg - 1 cap 3x daily for 5 days">Amoxicillin 500mg (Antibiotic)</option>
                        <option value="Cetirizine 10mg - 1 tab daily at bedtime">Cetirizine 10mg (Allergy/Cold)</option>
                    </select>

                    <label>Prescription</label>
                    <input name="prescription" value="{{ p['PRESCRIPTION'] }}">
                    
                    <label>Doctor Notes</label>
                    <input name="doctor_notes" value="{{ p['DOCTOR_NOTES'] }}">
                    
                    <button type="submit" style="background:var(--text); color:var(--card-bg); border:none; padding:6px 12px; border-radius:6px; font-weight:600; font-size:12px; cursor:pointer;">Update Clinical Data</button>
                </form>

                <div class="actions">
                    <a href="/status/{{ p['ID'] }}/In Triage" class="act-status">Triage</a>
                    <a href="/status/{{ p['ID'] }}/With Doctor" class="act-status">With Doctor</a>
                    <a href="/complete/{{ p['ID'] }}" class="act-complete">Complete</a>
                    {% if p['PAYMENT_STATUS'] != 'Paid' %}
                    <a href="/pay/{{ p['ID'] }}" class="act-pay">Mark Paid</a>
                    {% endif %}
                    <a href="/remove/{{ p['ID'] }}" class="act-remove">Remove</a>
                </div>
            </div>
            {% else %}
            <p style="color:#64748b; font-size:13px;">No patient records available.</p>
            {% endfor %}
        </div>

        <script>
            function openDrawer() {
                document.getElementById('sideDrawer').classList.add('open');
                document.getElementById('drawerOverlay').style.display = 'block';
            }

            function closeDrawer() {
                document.getElementById('sideDrawer').classList.remove('open');
                document.getElementById('drawerOverlay').style.display = 'none';
            }

            function toggleDarkMode() {
                document.body.classList.toggle('dark-mode');
            }

            function setTheme(themeName) {
                document.body.setAttribute('data-theme', themeName);
            }

            function filterPatients() {
                const input = document.getElementById('searchInput').value.toLowerCase();
                const cards = document.querySelectorAll('.patient-card');
                cards.forEach(card => {
                    const searchData = card.getAttribute('data-search');
                    card.style.display = searchData.includes(input) ? 'block' : 'none';
                });
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, patients=patients, rev=rev)

@app.route('/book', methods=['POST'])
def book():
    if session.get('user_type') == 'patient':
        patients = load_data()
        phone = session.get('patient_phone')
        name = session.get('patient_name')
        
        user = next((p for p in patients if p.get('PHONE NO.') == phone), {})
        password = user.get('PASSWORD', generate_password_hash('1234'))

        date_val = request.form.get('date')
        time_val = request.form.get('time')
        patients.append({
            'ID': str(int(time.time() * 1000)),
            'PATIENT NAME': name,
            'PHONE NO.': phone,
            'PASSWORD': password,
            'DATE': date_val,
            'TIME': time_val,
            'DEPARTMENT': request.form.get('department', 'General Practice'),
            'CHIEF COMPLAINTS': request.form.get('complaint'),
            'STATUS': 'Waiting',
            'AMOUNT': '500',
            'PAYMENT_METHOD': 'M-Pesa',
            'PAYMENT_STATUS': 'Unpaid',
            'VITALS': 'Pending Triage',
            'PRESCRIPTION': 'None assigned yet',
            'DOCTOR_NOTES': 'Pending evaluation',
            'BLOOD_GROUP': 'Unspecified',
            'ALLERGIES': 'None reported'
        })
        save_data(patients)
        send_sms_notification(phone, f"Hello {name}, your appointment is confirmed for {date_val} at {time_val}.")
        flash(f'Your appointment for {date_val} at {time_val} has been successfully submitted.')
    return redirect(url_for('patient_dashboard'))

@app.route('/staff/update_medical/<pid>', methods=['POST'])
def update_medical(pid):
    if session.get('user_type') == 'staff':
        patients = load_data()
        for p in patients:
            if p['ID'] == str(pid):
                p['VITALS'] = request.form.get('vitals', p['VITALS'])
                p['PRESCRIPTION'] = request.form.get('prescription', p['PRESCRIPTION'])
                p['DOCTOR_NOTES'] = request.form.get('doctor_notes', p['DOCTOR_NOTES'])
        save_data(patients)
    return redirect(url_for('staff_dashboard'))

@app.route('/receipt/<pid>')
def print_receipt(pid):
    patients = load_data()
    record = next((p for p in patients if p['ID'] == str(pid)), None)
    if not record:
        return "Receipt not found", 404

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Receipt - {{ record['PATIENT NAME'] }}</title>
        <style>
            body { font-family: monospace; padding: 20px; max-width: 400px; margin: 0 auto; border: 1px solid #ccc; }
            h2 { text-align: center; border-bottom: 2px dashed #000; padding-bottom: 10px; }
            .item { display: flex; justify-content: space-between; margin: 8px 0; }
            .total { border-top: 2px dashed #000; padding-top: 10px; font-weight: bold; font-size: 16px; }
            .btn { display: block; width: 100%; text-align: center; background: #000; color: #fff; padding: 10px; text-decoration: none; margin-top: 20px; }
            @media print { .btn { display: none; } }
        </style>
    </head>
    <body>
        <h2>HOSPITAL RECEIPT</h2>
        <p><strong>Receipt #:</strong> {{ record['ID'] }}</p>
        <p><strong>Patient:</strong> {{ record['PATIENT NAME'] }}</p>
        <p><strong>Phone:</strong> {{ record['PHONE NO.'] }}</p>
        <p><strong>Date:</strong> {{ record['DATE'] }} {{ record['TIME'] }}</p>
        <p><strong>Department:</strong> {{ record['DEPARTMENT'] }}</p>
        <hr>
        <div class="item">
            <span>Consultation Fee</span>
            <span>KES {{ record['AMOUNT'] }}</span>
        </div>
        <div class="item total">
            <span>TOTAL PAID ({{ record['PAYMENT_METHOD'] }})</span>
            <span>KES {{ record['AMOUNT'] }}</span>
        </div>
        <p><strong>Status:</strong> {{ record['PAYMENT_STATUS'] }}</p>
        <a href="javascript:window.print()" class="btn">Print / Save PDF</a>
    </body>
    </html>
    """
    return render_template_string(html, record=record)

@app.route('/patient/cancel/<pid>')
def patient_cancel(pid):
    if session.get('user_type') == 'patient':
        patients = [p for p in load_data() if p['ID'] != str(pid)]
        save_data(patients)
        flash('Appointment cancelled.')
    return redirect(url_for('patient_dashboard'))

@app.route('/add', methods=['POST'])
def add_patient():
    patients = load_data()
    now = datetime.now()
    patients.append({
        'ID': str(int(time.time() * 1000)),
        'PATIENT NAME': request.form.get('name'),
        'PHONE NO.': request.form.get('phone'),
        'PASSWORD': generate_password_hash('1234'),
        'DATE': now.strftime('%Y-%m-%d'),
        'TIME': now.strftime('%H:%M'),
        'DEPARTMENT': request.form.get('department', 'General Practice'),
        'CHIEF COMPLAINTS': request.form.get('complaint'),
        'STATUS': 'Waiting',
        'AMOUNT': request.form.get('amount', '500'),
        'PAYMENT_METHOD': request.form.get('payment_method', 'M-Pesa'),
        'PAYMENT_STATUS': request.form.get('payment_status', 'Paid'),
        'VITALS': 'BP: 120/80 | Temp: 36.6°C',
        'PRESCRIPTION': 'None assigned yet',
        'DOCTOR_NOTES': 'Initial registration',
        'BLOOD_GROUP': 'Unspecified',
        'ALLERGIES': 'None reported'
    })
    save_data(patients)
    return redirect(url_for('staff_dashboard'))

@app.route('/status/<pid>/<new_status>')
def update_status(pid, new_status):
    patients = load_data()
    for p in patients:
        if p['ID'] == str(pid):
            p['STATUS'] = new_status
            send_sms_notification(p['PHONE NO.'], f"Hello {p['PATIENT NAME']}, your appointment status is now: {new_status}.")
    save_data(patients)
    return redirect(url_for('staff_dashboard'))

@app.route('/complete/<pid>')
def mark_complete(pid):
    return update_status(pid, 'Completed')

@app.route('/pay/<pid>')
def mark_paid(pid):
    patients = load_data()
    for p in patients:
        if p['ID'] == str(pid):
            p['PAYMENT_STATUS'] = 'Paid'
    save_data(patients)
    return redirect(url_for('staff_dashboard'))

@app.route('/remove/<pid>')
def remove_patient(pid):
    patients = [p for p in load_data() if p['ID'] != str(pid)]
    save_data(patients)
    return redirect(url_for('staff_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('patient_login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)





























