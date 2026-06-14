import os, sqlite3, re, random, string, math, requests, json
from datetime import date, timedelta, datetime
from collections import defaultdict
from flask import Flask, render_template_string, request, redirect, url_for, session, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from PIL import Image

# ============================================================
# APP CONFIGURATION
# ============================================================
app = Flask(__name__)
app.secret_key = 'rockabyconnect-secret-key-change-in-production-2025'
app.permanent_session_lifetime = timedelta(days=30)

# Admin password for the separate admin panel
ADMIN_PASSWORD = 'Trythorous2909@1707#!'

# File upload settings
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# Skill suggestions
SKILL_SUGGESTIONS = [
    'Plumbing', 'Electrical', 'Carpentry', 'Painting', 'Cleaning',
    'Tutoring', 'Graphic Design', 'Web Development', 'Tailoring',
    'Cooking', 'Driving', 'Bricklaying', 'Construction', 'Boda Rider',
    'Maid', 'Gardening', 'Security Guard', 'Welding', 'Salon/Hair dressing',
    'Farming', 'Other'
]

FREELANCER_STATUSES = ['Available', 'Occupied', 'On Leave']
VENDOR_STATUSES = ['Open', 'Closed', 'Away']

DB_PATH = os.path.join(os.getcwd(), 'rockabyconnect.db')

# ============================================================
# DATABASE FUNCTIONS
# ============================================================
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA busy_timeout = 5000;")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )''')
    
    # Providers table
    c.execute('''CREATE TABLE IF NOT EXISTS providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        skills TEXT,
        district TEXT,
        village TEXT,
        bio TEXT,
        profile_pic TEXT,
        status TEXT DEFAULT 'Available',
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    c.execute("PRAGMA table_info(providers)")
    prov_cols = [col[1] for col in c.fetchall()]
    for col in ['skills', 'village', 'featured_expiry']:
        if col not in prov_cols:
            c.execute(f"ALTER TABLE providers ADD COLUMN {col} TEXT")
    
    # Vendors table
    c.execute('''CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        business_name TEXT NOT NULL,
        district TEXT,
        village TEXT,
        landmark TEXT,
        bio TEXT,
        vendor_image TEXT,
        vendor_image2 TEXT,
        vendor_image3 TEXT,
        status TEXT DEFAULT 'Open',
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    c.execute("PRAGMA table_info(vendors)")
    vend_cols = [col[1] for col in c.fetchall()]
    for col in ['landmark', 'vendor_image2', 'vendor_image3', 'featured_expiry']:
        if col not in vend_cols:
            c.execute(f"ALTER TABLE vendors ADD COLUMN {col} TEXT")
    
    # Jobs table
    c.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employer_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        company TEXT,
        description TEXT,
        location TEXT,
        village TEXT,
        contact TEXT,
        status TEXT DEFAULT 'Open',
        posted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        job_image TEXT,
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(employer_id) REFERENCES users(id)
    )''')
    
    c.execute("PRAGMA table_info(jobs)")
    job_cols = [col[1] for col in c.fetchall()]
    for col in ['village', 'job_image', 'featured', 'featured_expiry']:
        if col not in job_cols:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
    
    # Reviews table
    c.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id INTEGER NOT NULL,
        reviewer_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(provider_id) REFERENCES providers(id),
        FOREIGN KEY(reviewer_id) REFERENCES users(id)
    )''')
    
    # Boost requests table
    c.execute('''CREATE TABLE IF NOT EXISTS boost_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        transaction_id TEXT NOT NULL,
        plan TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        boost_type TEXT DEFAULT 'profile',
        item_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # Notifications table
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # Payment tables - Integrated with RockabyConnect
    c.execute('''CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL,
        price_ugx INTEGER NOT NULL,
        is_active INTEGER DEFAULT 1,
        is_public INTEGER DEFAULT 1,
        speed_down TEXT,
        speed_up TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        plan_id INTEGER,
        payment_method TEXT DEFAULT 'sms',
        phone_number TEXT,
        used INTEGER DEFAULT 0,
        used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(plan_id) REFERENCES plans(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS voucher_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone_number TEXT NOT NULL,
        plan_id INTEGER,
        raw_sms TEXT NOT NULL,
        transaction_id TEXT,
        amount INTEGER,
        recipient TEXT,
        payment_date TEXT,
        status TEXT DEFAULT 'pending',
        voucher_code TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(plan_id) REFERENCES plans(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS yo_tx (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_ref TEXT UNIQUE,
        phone TEXT,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        voucher_code TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Check if plans exist
    c.execute("SELECT COUNT(*) FROM plans")
    if c.fetchone()[0] == 0:
        default_plans = [
            ('1 Hour', 60, 500),
            ('3 Hours', 180, 1000),
            ('24 Hours', 1440, 2000),
            ('Weekly', 10080, 8000),
            ('Monthly', 43200, 25000)
        ]
        for name, mins, price in default_plans:
            c.execute("INSERT INTO plans (name, duration_minutes, price_ugx, is_public) VALUES (?,?,?,1)", (name, mins, price))
    
    # Insert default admin user
    c.execute("SELECT COUNT(*) FROM users WHERE phone='256751318876'")
    if c.fetchone()[0] == 0:
        hashed = generate_password_hash('admin123')
        c.execute("INSERT INTO users (phone, name, password_hash) VALUES ('256751318876', 'RockabyTech Admin', ?)", (hashed,))
    
    conn.commit()
    conn.close()

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_resized_image(file, max_width=800):
    filename = secure_filename(file.filename)
    base, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.gif'):
        ext = '.jpg'
    new_filename = f"{base}_{os.urandom(4).hex()}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
    
    img = Image.open(file.stream)
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.save(filepath, quality=85)
    return new_filename

def whatsapp_link(phone):
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('0'):
        digits = '256' + digits[1:]
    elif not digits.startswith('256'):
        digits = '256' + digits
    return f"https://wa.me/{digits}"

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def is_featured_now(featured_flag, expiry_date):
    if not featured_flag:
        return False
    if expiry_date is None:
        return True
    return date.today() <= date.fromisoformat(expiry_date)

def generate_voucher_code():
    return 'CONNECT-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) + '-' + \
           ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) + '-' + \
           ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def clean_phone_number(num):
    digits = ''.join(filter(str.isdigit, num))
    if digits.startswith('0'):
        digits = '256' + digits[1:]
    elif not digits.startswith('256'):
        digits = '256' + digits
    return digits

def add_notification(user_id, type, message):
    try:
        db = get_db()
        db.execute("INSERT INTO notifications (user_id, type, message) VALUES (?,?,?)", (user_id, type, message))
        db.commit()
    except Exception as e:
        print(f"Notification failed: {e}")

def get_provider_count():
    db = get_db()
    return db.execute("SELECT COUNT(*) FROM providers").fetchone()[0]

def get_open_jobs_count():
    db = get_db()
    return db.execute("SELECT COUNT(*) FROM jobs WHERE status='Open'").fetchone()[0]

def get_pending_boosts_count():
    db = get_db()
    return db.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'").fetchone()[0]

# ============================================================
# PAYMENT HELPERS
# ============================================================
def parse_mtn_sms(sms):
    tid = re.search(r'ID:\s*(\d+)', sms)
    amount = re.search(r'UGX\s*([\d,]+)', sms)
    recipient_name = re.search(r'to\s+(.+?),', sms)
    number_match = re.search(r'to\s+.+?[, ]+(\d{10,12})', sms)
    date_str = re.search(r'on\s+(\d{4}-\d{2}-\d{2})', sms)
    return {
        'tid': tid.group(1) if tid else None,
        'amount': int(amount.group(1).replace(',', '')) if amount else None,
        'recipient_name': recipient_name.group(1).strip() if recipient_name else None,
        'recipient_number': number_match.group(1) if number_match else None,
        'date': date_str.group(1) if date_str else None
    }

def parse_airtel_sms(sms):
    tid = re.search(r'TID\s*(\d+)', sms)
    amount = re.search(r'UGX\s*([\d,]+)', sms)
    recipient_match = re.search(r'to\s+(.+?)\s+on\s+(\d+)', sms, re.IGNORECASE)
    if recipient_match:
        recipient_name = recipient_match.group(1).strip()
        recipient_number = recipient_match.group(2).strip()
    else:
        recipient_match = re.search(r'to\s+(.+?)\s+\d', sms)
        recipient_name = recipient_match.group(1).strip() if recipient_match else None
        recipient_number = None
    date_str = re.search(r'Date\s+(\d{2}-[A-Za-z]+-\d{4}\s+\d{2}:\d{2})', sms)
    return {
        'tid': tid.group(1) if tid else None,
        'amount': int(amount.group(1).replace(',', '')) if amount else None,
        'recipient_name': recipient_name,
        'recipient_number': recipient_number,
        'date': date_str.group(1) if date_str else None
    }

# ============================================================
# GLASSMORPHISM BASE TEMPLATE - PROPER JINJA2 RENDERING
# ============================================================
base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RockabyConnect – {{title}}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        :root {
            --primary: #f5af19; --primary-dark: #e09e15;
            --bg: #f0f4f8; --card-bg: rgba(255,255,255,0.85);
            --glass-border: rgba(255,255,255,0.3);
            --text: #1a1a1a; --text-secondary: #666;
            --border: #e0e0e0;
            --radius: 20px; --shadow: 0 8px 32px rgba(0,0,0,0.08);
        }
        .dark-mode {
            --bg: #0f172a; --card-bg: rgba(30,41,59,0.85);
            --glass-border: rgba(255,255,255,0.08);
            --text: #f1f5f9; --text-secondary: #94a3b8;
            --border: #334155;
        }
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            transition: all 0.3s;
        }
        .navbar {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--glass-border);
            padding: 16px 24px;
            position: sticky;
            top: 0;
            z-index: 1000;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 15px;
        }
        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
        }
        .logo-icon {
            width: 45px;
            height: 45px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
        }
        .logo-text {
            font-size: 1.3rem;
            font-weight: 800;
        }
        .logo-text span { color: var(--primary); }
        .logo-sub {
            font-size: 0.7rem;
            color: var(--text-secondary);
        }
        .nav-links {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }
        .nav-links a {
            color: var(--text-secondary);
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 12px;
            transition: all 0.2s;
        }
        .nav-links a:hover, .nav-links a.active {
            background: rgba(245, 175, 25, 0.15);
            color: var(--primary);
        }
        .theme-toggle {
            background: rgba(245, 175, 25, 0.1);
            border: none;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            cursor: pointer;
            font-size: 1.2rem;
            color: var(--text);
        }
        .hamburger {
            display: none;
            background: none;
            border: none;
            font-size: 1.8rem;
            cursor: pointer;
            color: var(--text);
        }
        .container { max-width: 1200px; margin: 24px auto; padding: 0 20px; }
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: var(--radius);
            padding: 28px;
            margin-bottom: 24px;
            box-shadow: var(--shadow);
            border: 1px solid var(--glass-border);
            transition: all 0.3s;
        }
        .card:hover { transform: translateY(-4px); }
        .card-header {
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--primary);
        }
        .hero {
            background: linear-gradient(135deg, rgba(245,175,25,0.15), rgba(26,115,232,0.15));
            border-radius: var(--radius);
            padding: 60px 40px;
            text-align: center;
            margin-bottom: 30px;
        }
        .hero h1 {
            font-size: 2.5rem;
            margin-bottom: 15px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .btn {
            display: inline-block;
            padding: 12px 28px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
        .btn-outline {
            background: transparent;
            border: 2px solid var(--primary);
            color: var(--primary);
        }
        .btn-whatsapp {
            background: linear-gradient(135deg, #25D366, #128C7E);
        }
        .btn-small { padding: 6px 14px; font-size: 0.85rem; }
        .btn-danger { background: linear-gradient(135deg, #dc3545, #c82333); }
        .btn-success { background: linear-gradient(135deg, #28a745, #20c997); }
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: var(--radius);
            padding: 28px;
            text-align: center;
            border: 1px solid var(--glass-border);
        }
        .stat-card h3 {
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--primary);
        }
        .category-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
            justify-content: center;
        }
        .chip {
            background: rgba(245, 175, 25, 0.2);
            color: var(--text);
            font-weight: 600;
            padding: 6px 18px;
            border-radius: 30px;
            text-decoration: none;
            transition: all 0.2s;
        }
        .chip:hover {
            background: var(--primary);
            color: white;
        }
        .provider-card, .job-card, .vendor-card {
            display: flex;
            align-items: center;
            gap: 20px;
            padding: 20px 0;
            border-bottom: 1px solid var(--border);
        }
        .provider-card:last-child, .job-card:last-child, .vendor-card:last-child {
            border-bottom: none;
        }
        .profile-pic {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            object-fit: cover;
            border: 3px solid var(--primary);
        }
        .vendor-img {
            width: 100px;
            height: 100px;
            object-fit: cover;
            border-radius: 12px;
        }
        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.7rem;
            font-weight: 600;
            margin-left: 8px;
        }
        .badge-available { background: #28a745; }
        .badge-occupied { background: #ffc107; color: #333; }
        .badge-leave { background: #6c757d; }
        .badge-open { background: #17a2b8; }
        .voucher-code {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 12px 18px;
            border-radius: 10px;
            display: inline-block;
            font-family: monospace;
        }
        .copy-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 6px;
            cursor: pointer;
            margin-left: 10px;
        }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }
        th { color: var(--primary); }
        label { display: block; margin-top: 18px; font-weight: 600; }
        input, textarea, select {
            width: 100%;
            padding: 12px 16px;
            border-radius: 12px;
            border: 1px solid var(--border);
            background: var(--card-bg);
            color: var(--text);
        }
        .whatsapp-float {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: linear-gradient(135deg, #25D366, #128C7E);
            color: white;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            z-index: 999;
            text-decoration: none;
        }
        footer {
            text-align: center;
            padding: 30px;
            color: var(--text-secondary);
            border-top: 1px solid var(--border);
            margin-top: 40px;
        }
        .alert { padding: 14px 20px; border-radius: 12px; margin-bottom: 20px; }
        .alert-success { background: rgba(40,167,69,0.15); border: 1px solid rgba(40,167,69,0.3); color: #28a745; }
        .alert-error { background: rgba(220,53,69,0.15); border: 1px solid rgba(220,53,69,0.3); color: #dc3545; }
        @media (max-width: 768px) {
            .nav-links { display: none; width: 100%; flex-direction: column; }
            .nav-links.open { display: flex; }
            .hamburger { display: block; }
            .provider-card, .job-card, .vendor-card { flex-direction: column; align-items: flex-start; }
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <a href="/" class="logo">
            <div class="logo-icon">🔗</div>
            <div>
                <div class="logo-text">ROCKABY<span>CONNECT</span></div>
                <div class="logo-sub">Connecting Skills, Building Uganda</div>
            </div>
        </a>
        <button class="hamburger" onclick="toggleMenu()">☰</button>
        <div class="nav-links" id="navMenu">
            <a href="/" class="active">Home</a>
            {% if session.user_id %}
                <a href="/dashboard">Dashboard</a>
            {% endif %}
            <a href="/list">Find Skills</a>
            <a href="/jobs">Jobs</a>
            <a href="/vendors">Vendors</a>
            <a href="/plans">Internet Plans</a>
            {% if session.user_id %}
                <a href="/logout">Logout</a>
            {% else %}
                <a href="/login">Login</a>
                <a href="/signup">Sign Up</a>
            {% endif %}
            <button class="theme-toggle" onclick="toggleTheme()">🌓</button>
        </div>
    </nav>
    <div class="container">{{content}}</div>
    <footer>&copy; 2025 RockabyTech – Connecting Skills, Building Uganda 🇺🇬</footer>
    <a href="https://wa.me/256751318876" target="_blank" class="whatsapp-float">💬</a>
    <script>
        function toggleMenu() { document.getElementById('navMenu').classList.toggle('open'); }
        function toggleTheme() { 
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('theme', document.body.classList.contains('dark-mode') ? 'dark' : 'light');
        }
        if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');
    </script>
</body>
</html>
"""

def render_page(title, content):
    from flask import render_template_string
    return render_template_string(base_template, title=title, content=content, session=session)

# ============================================================
# HOME ROUTE
# ============================================================
@app.route('/')
def home():
    provider_count = get_provider_count()
    open_jobs = get_open_jobs_count()
    
    content = f"""
    <div class="hero">
        <h1>✨ Get Work Done – or Get Paid</h1>
        <p>Uganda's premier freelance marketplace. Connect with trusted skilled workers near you.</p>
        <div style="display: flex; gap: 15px; justify-content: center; flex-wrap: wrap;">
            <a href="/offer-skill" class="btn"><i class="fas fa-user-plus"></i> Offer Your Skill</a>
            <a href="/post-job" class="btn btn-outline"><i class="fas fa-briefcase"></i> Post a Job</a>
            <a href="/plans" class="btn btn-outline"><i class="fas fa-wifi"></i> Buy Internet</a>
        </div>
        <div class="category-chips">
            <span>Popular:</span>
            <a href="/list?search=Boda+Rider" class="chip">Boda Rider</a>
            <a href="/list?search=Maid" class="chip">Maid</a>
            <a href="/list?search=Plumbing" class="chip">Plumbing</a>
            <a href="/list?search=Electrical" class="chip">Electrical</a>
            <a href="/list?search=Carpentry" class="chip">Carpentry</a>
        </div>
    </div>
    <div class="stat-grid">
        <div class="stat-card"><h3>{provider_count}</h3><small>Skilled Workers</small></div>
        <div class="stat-card"><h3>{open_jobs}</h3><small>Open Jobs</small></div>
        <div class="stat-card"><h3>10K+</h3><small>Monthly Visitors</small></div>
    </div>
    <div class="card">
        <div class="card-header">📖 How It Works</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; text-align: center;">
            <div><div style="font-size: 2rem;">🔍</div><h3>1. Find Skills</h3><p>Browse verified workers</p></div>
            <div><div style="font-size: 2rem;">📝</div><h3>2. Post a Job</h3><p>Describe what you need</p></div>
            <div><div style="font-size: 2rem;">💬</div><h3>3. Connect</h3><p>Chat on WhatsApp</p></div>
        </div>
    </div>
    """
    return render_page("Home", content)

# ============================================================
# AUTHENTICATION ROUTES
# ============================================================
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        name = request.form['name'].strip()
        password = request.form['password']
        if not phone or not name or not password:
            return render_page("Sign Up", '<div class="card"><div class="alert alert-error">All fields required.</div><a href="/signup">Try again</a></div>')
        hashed = generate_password_hash(password)
        try:
            db = get_db()
            db.execute("INSERT INTO users (phone, name, password_hash) VALUES (?, ?, ?)", (phone, name, hashed))
            db.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return render_page("Sign Up", '<div class="card"><div class="alert alert-error">Phone already registered.</div><a href="/login">Login</a></div>')
    
    content = """
    <div class="card" style="max-width: 500px; margin: 0 auto;">
        <div class="card-header">📝 Create Your Free Account</div>
        <form method="POST">
            <label>Full Name *</label>
            <input type="text" name="name" required>
            <label>Phone Number *</label>
            <input type="tel" name="phone" required placeholder="0751318876">
            <label>Password *</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Sign Up</button>
        </form>
        <p style="margin-top: 20px; text-align: center;">Already have an account? <a href="/login">Login</a></p>
    </div>
    """
    return render_page("Sign Up", content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT id, name, password_hash FROM users WHERE phone=?", (phone,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_phone'] = phone
            return redirect(url_for('dashboard'))
        return render_page("Login", '<div class="card"><div class="alert alert-error">Invalid credentials.</div><a href="/login">Try again</a></div>')
    
    content = """
    <div class="card" style="max-width: 500px; margin: 0 auto;">
        <div class="card-header">🔐 Login</div>
        <form method="POST">
            <label>Phone Number</label>
            <input type="tel" name="phone" required>
            <label>Password</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Login</button>
        </form>
        <p style="margin-top: 20px; text-align: center;">No account? <a href="/signup">Sign Up</a></p>
    </div>
    """
    return render_page("Login", content)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/offer-skill')
def offer_skill():
    if 'user_id' not in session:
        return redirect('/login')
    db = get_db()
    provider = db.execute("SELECT id FROM providers WHERE user_id=?", (session['user_id'],)).fetchone()
    if provider:
        return redirect('/edit-profile')
    return redirect('/create-profile')

# ============================================================
# USER DASHBOARD (No Admin Features Here!)
# ============================================================
@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    db = get_db()
    
    provider = db.execute("SELECT * FROM providers WHERE user_id=?", (user_id,)).fetchone()
    vendor = db.execute("SELECT * FROM vendors WHERE user_id=?", (user_id,)).fetchone()
    jobs = db.execute("SELECT id, title, status FROM jobs WHERE employer_id=? ORDER BY id DESC", (user_id,)).fetchall()
    
    profile_section = ""
    if provider:
        status_class = provider['status'].lower().replace(' ', '-')
        profile_section = f"""
        <div class="card">
            <div class="card-header"><i class="fas fa-user-cog"></i> My Freelancer Profile</div>
            <p><strong>Skills:</strong> {provider['skills'] or 'Not set'}</p>
            <p><strong>Location:</strong> {provider['district'] or 'Not set'}</p>
            <p><strong>Status:</strong> <span class="badge badge-{status_class}">{provider['status']}</span></p>
            <div style="display: flex; gap: 10px; margin-top: 15px;">
                <a href="/edit-profile" class="btn btn-small">Edit Profile</a>
                <a href="/boost" class="btn btn-small" style="background: var(--primary-dark);">Boost Profile</a>
            </div>
        </div>
        """
    else:
        profile_section = """
        <div class="card">
            <p>You haven't created a freelancer profile yet.</p>
            <a href="/create-profile" class="btn">Create Freelancer Profile</a>
        </div>
        """
    
    vendor_section = ""
    if vendor:
        vstatus_class = vendor['status'].lower()
        vendor_section = f"""
        <div class="card">
            <div class="card-header"><i class="fas fa-store"></i> My Vendor Profile</div>
            <p><strong>Business:</strong> {vendor['business_name']}</p>
            <p><strong>Location:</strong> {vendor['district'] or 'Not set'}</p>
            <p><strong>Status:</strong> <span class="badge badge-{vstatus_class}">{vendor['status']}</span></p>
            <div style="display: flex; gap: 10px; margin-top: 15px;">
                <a href="/edit-vendor-profile" class="btn btn-small">Edit Vendor</a>
                <a href="/boost-vendor" class="btn btn-small" style="background: var(--primary-dark);">Boost Vendor</a>
            </div>
        </div>
        """
    else:
        vendor_section = """
        <div class="card">
            <p>You haven't created a vendor profile yet.</p>
            <a href="/create-vendor-profile" class="btn">Create Vendor Profile</a>
        </div>
        """
    
    jobs_html = ""
    if jobs:
        for job in jobs:
            badge_class = 'open' if job['status'] == 'Open' else 'closed'
            jobs_html += f"""
            <div style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--border);">
                <span>{job['title']} <span class="badge badge-{badge_class}">{job['status']}</span></span>
                <div><a href="/edit-job/{job['id']}" class="btn btn-small btn-outline">Edit</a> <a href="/boost-job/{job['id']}" class="btn btn-small">Boost</a></div>
            </div>
            """
    else:
        jobs_html = "<p>No jobs posted yet.</p>"
    
    dashboard_content = f"""
    <div class="card">
        <div class="card-header">Welcome, {session['user_name']}!</div>
        <p>Manage your freelance presence, vendor profile, and job postings from one place.</p>
    </div>
    {profile_section}
    {vendor_section}
    <div class="card">
        <div class="card-header">My Job Postings</div>
        {jobs_html}
        <a href="/post-job" class="btn" style="margin-top: 15px;">Post a New Job</a>
    </div>
    """
    return render_page("Dashboard", dashboard_content)

# ============================================================
# FREELANCER PROFILE ROUTES
# ============================================================
@app.route('/create-profile', methods=['GET', 'POST'])
@login_required
def create_profile():
    if request.method == 'POST':
        skills = request.form['skills'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '')
        bio = request.form.get('bio', '')
        status = request.form.get('status', 'Available')
        file = request.files.get('profile_pic')
        filename = None
        if file and allowed_file(file.filename):
            filename = save_resized_image(file)
        
        db = get_db()
        db.execute("INSERT INTO providers (user_id, skills, district, village, bio, profile_pic, status) VALUES (?,?,?,?,?,?,?)",
                   (session['user_id'], skills, district, village, bio, filename, status))
        db.commit()
        return redirect('/dashboard')
    
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in FREELANCER_STATUSES])
    content = f"""
    <div class="card">
        <div class="card-header">Create Your Freelancer Profile</div>
        <form method="POST" enctype="multipart/form-data">
            <label>Skills * (comma separated)</label>
            <input type="text" name="skills" required placeholder="Plumbing, Electrical, Carpentry">
            <label>District/City *</label>
            <input type="text" name="district" required>
            <label>Village/Area</label>
            <input type="text" name="village">
            <label>Short Bio</label>
            <textarea name="bio" rows="3"></textarea>
            <label>Profile Picture</label>
            <input type="file" name="profile_pic" accept="image/*">
            <label>Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Create Profile</button>
        </form>
    </div>
    """
    return render_page("Create Profile", content)

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    db = get_db()
    provider = db.execute("SELECT * FROM providers WHERE user_id=?", (session['user_id'],)).fetchone()
    if not provider:
        return redirect('/create-profile')
    
    if request.method == 'POST':
        skills = request.form['skills'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '')
        bio = request.form.get('bio', '')
        status = request.form.get('status', 'Available')
        file = request.files.get('profile_pic')
        if file and allowed_file(file.filename):
            filename = save_resized_image(file)
            db.execute("UPDATE providers SET skills=?, district=?, village=?, bio=?, profile_pic=?, status=? WHERE user_id=?",
                       (skills, district, village, bio, filename, status, session['user_id']))
        else:
            db.execute("UPDATE providers SET skills=?, district=?, village=?, bio=?, status=? WHERE user_id=?",
                       (skills, district, village, bio, status, session['user_id']))
        db.commit()
        return redirect('/dashboard')
    
    status_options = ''.join([f'<option value="{s}" {"selected" if s==provider["status"] else ""}>{s}</option>' for s in FREELANCER_STATUSES])
    content = f"""
    <div class="card">
        <div class="card-header">Edit Your Freelancer Profile</div>
        <form method="POST" enctype="multipart/form-data">
            <label>Skills</label>
            <input type="text" name="skills" value="{provider['skills'] or ''}" required>
            <label>District/City</label>
            <input type="text" name="district" value="{provider['district'] or ''}" required>
            <label>Village/Area</label>
            <input type="text" name="village" value="{provider['village'] or ''}">
            <label>Bio</label>
            <textarea name="bio" rows="3">{provider['bio'] or ''}</textarea>
            <label>Profile Picture</label>
            <input type="file" name="profile_pic" accept="image/*">
            <label>Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Save Changes</button>
        </form>
    </div>
    """
    return render_page("Edit Profile", content)

# ============================================================
# VENDOR PROFILE ROUTES
# ============================================================
@app.route('/create-vendor-profile', methods=['GET', 'POST'])
@login_required
def create_vendor_profile():
    if request.method == 'POST':
        business_name = request.form['business_name'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '')
        landmark = request.form.get('landmark', '')
        bio = request.form.get('bio', '')
        status = request.form.get('status', 'Open')
        
        filenames = [None, None, None]
        for idx, field in enumerate(['vendor_image', 'vendor_image2', 'vendor_image3']):
            file = request.files.get(field)
            if file and allowed_file(file.filename):
                filenames[idx] = save_resized_image(file)
        
        db = get_db()
        db.execute("INSERT INTO vendors (user_id, business_name, district, village, landmark, bio, vendor_image, vendor_image2, vendor_image3, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (session['user_id'], business_name, district, village, landmark, bio, filenames[0], filenames[1], filenames[2], status))
        db.commit()
        return redirect('/dashboard')
    
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in VENDOR_STATUSES])
    content = f"""
    <div class="card">
        <div class="card-header">Create Vendor Profile</div>
        <form method="POST" enctype="multipart/form-data">
            <label>Business Name *</label>
            <input type="text" name="business_name" required>
            <label>District/City *</label>
            <input type="text" name="district" required>
            <label>Village/Area</label>
            <input type="text" name="village">
            <label>Landmark</label>
            <input type="text" name="landmark">
            <label>Description</label>
            <textarea name="bio" rows="3"></textarea>
            <label>Main Photo</label>
            <input type="file" name="vendor_image" accept="image/*">
            <label>Additional Photos</label>
            <input type="file" name="vendor_image2" accept="image/*">
            <input type="file" name="vendor_image3" accept="image/*">
            <label>Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Create Vendor Profile</button>
        </form>
    </div>
    """
    return render_page("Create Vendor Profile", content)

@app.route('/edit-vendor-profile', methods=['GET', 'POST'])
@login_required
def edit_vendor_profile():
    db = get_db()
    vendor = db.execute("SELECT * FROM vendors WHERE user_id=?", (session['user_id'],)).fetchone()
    if not vendor:
        return redirect('/create-vendor-profile')
    
    if request.method == 'POST':
        business_name = request.form['business_name'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '')
        landmark = request.form.get('landmark', '')
        bio = request.form.get('bio', '')
        status = request.form.get('status', 'Open')
        
        current_images = [vendor['vendor_image'], vendor['vendor_image2'], vendor['vendor_image3']]
        for idx, field in enumerate(['vendor_image', 'vendor_image2', 'vendor_image3']):
            file = request.files.get(field)
            if file and allowed_file(file.filename):
                current_images[idx] = save_resized_image(file)
        
        db.execute("UPDATE vendors SET business_name=?, district=?, village=?, landmark=?, bio=?, vendor_image=?, vendor_image2=?, vendor_image3=?, status=? WHERE user_id=?",
                   (business_name, district, village, landmark, bio, current_images[0], current_images[1], current_images[2], status, session['user_id']))
        db.commit()
        return redirect('/dashboard')
    
    status_options = ''.join([f'<option value="{s}" {"selected" if s==vendor["status"] else ""}>{s}</option>' for s in VENDOR_STATUSES])
    content = f"""
    <div class="card">
        <div class="card-header">Edit Vendor Profile</div>
        <form method="POST" enctype="multipart/form-data">
            <label>Business Name</label>
            <input type="text" name="business_name" value="{vendor['business_name']}" required>
            <label>District/City</label>
            <input type="text" name="district" value="{vendor['district'] or ''}" required>
            <label>Village/Area</label>
            <input type="text" name="village" value="{vendor['village'] or ''}">
            <label>Landmark</label>
            <input type="text" name="landmark" value="{vendor['landmark'] or ''}">
            <label>Description</label>
            <textarea name="bio" rows="3">{vendor['bio'] or ''}</textarea>
            <label>Main Photo</label>
            <input type="file" name="vendor_image" accept="image/*">
            <label>Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Save Changes</button>
        </form>
    </div>
    """
    return render_page("Edit Vendor Profile", content)

# ============================================================
# VENDOR LISTING
# ============================================================
@app.route('/vendors')
def list_vendors():
    db = get_db()
    vendors = db.execute("""
        SELECT v.id, v.business_name, v.district, v.village, v.landmark, v.bio, v.vendor_image, v.status, v.featured, v.featured_expiry, u.phone
        FROM vendors v JOIN users u ON v.user_id = u.id
        ORDER BY v.featured DESC, v.id DESC
    """).fetchall()
    
    cards = ""
    for v in vendors:
        status_class = v['status'].lower()
        img_url = f"/static/uploads/{v['vendor_image']}" if v['vendor_image'] else ""
        loc_display = f"{v['district']}{', ' + v['village'] if v['village'] else ''}"
        cards += f"""
        <div class="vendor-card">
            <img src="{img_url or 'https://placehold.co/100x100?text=🏪'}" class="vendor-img">
            <div class="vendor-info">
                <h3><a href="/vendor/{v['id']}">{v['business_name']}</a> <span class="badge badge-{status_class}">{v['status']}</span></h3>
                <p>{loc_display}</p>
                <p>{v['bio'][:100] if v['bio'] else ''}</p>
                <a href="/vendor/{v['id']}" class="btn btn-small">View Details</a>
            </div>
        </div>"""
    
    content = f"""
    <div class="card">
        <div class="card-header">Local Vendors & Shops</div>
        <div id="vendorCards">{cards}</div>
    </div>
    """
    return render_page("Vendors", content)

@app.route('/vendor/<int:vendor_id>')
def vendor_detail(vendor_id):
    db = get_db()
    v = db.execute("SELECT v.*, u.phone FROM vendors v JOIN users u ON v.user_id = u.id WHERE v.id=?", (vendor_id,)).fetchone()
    if not v:
        return "Vendor not found", 404
    
    img_url = f"/static/uploads/{v['vendor_image']}" if v['vendor_image'] else ""
    content = f"""
    <div class="card">
        <div class="card-header">{v['business_name']}</div>
        <img src="{img_url}" style="width: 100%; max-height: 300px; object-fit: cover; border-radius: 16px; margin-bottom: 20px;">
        <p><strong>Location:</strong> {v['district']}{', ' + v['village'] if v['village'] else ''}</p>
        <p><strong>Description:</strong> {v['bio'] or 'No description'}</p>
        <p><strong>Status:</strong> <span class="badge badge-{v['status'].lower()}">{v['status']}</span></p>
        <a href="{whatsapp_link(v['phone'])}" target="_blank" class="btn btn-whatsapp">Contact on WhatsApp</a>
    </div>
    """
    return render_page(v['business_name'], content)

# ============================================================
# FREELANCER LISTING
# ============================================================
@app.route('/list')
def list_providers():
    db = get_db()
    providers = db.execute("""
        SELECT p.id, u.name, p.skills, u.phone, p.district, p.village, p.bio, p.profile_pic, p.status, p.featured, p.featured_expiry
        FROM providers p JOIN users u ON p.user_id = u.id
        ORDER BY p.featured DESC, p.id DESC
    """).fetchall()
    
    cards = ""
    for p in providers:
        status_class = p['status'].lower().replace(' ', '-')
        img_url = f"/static/uploads/{p['profile_pic']}" if p['profile_pic'] else ""
        cards += f"""
        <div class="provider-card">
            <img src="{img_url or 'https://placehold.co/80x80?text=👤'}" class="profile-pic">
            <div class="provider-info">
                <h3><a href="/provider/{p['id']}">{p['name']}</a> <span class="badge badge-{status_class}">{p['status']}</span></h3>
                <p><strong>{p['skills'] or 'No skills'}</strong> · {p['district'] or 'Uganda'}</p>
                <p>{p['bio'][:100] if p['bio'] else ''}</p>
                <a href="/provider/{p['id']}" class="btn btn-small">View Profile</a>
            </div>
        </div>"""
    
    content = f"""
    <div class="card">
        <div class="card-header">Find Skilled Workers</div>
        <div id="providerCards">{cards}</div>
    </div>
    """
    return render_page("Find Freelancers", content)

@app.route('/provider/<int:provider_id>')
def provider_detail(provider_id):
    db = get_db()
    p = db.execute("SELECT p.*, u.name, u.phone FROM providers p JOIN users u ON p.user_id = u.id WHERE p.id=?", (provider_id,)).fetchone()
    if not p:
        return "Provider not found", 404
    
    img_url = f"/static/uploads/{p['profile_pic']}" if p['profile_pic'] else ""
    content = f"""
    <div class="card">
        <div class="card-header">{p['name']}</div>
        <img src="{img_url}" class="profile-pic" style="width: 120px; height: 120px;">
        <p><strong>Skills:</strong> {p['skills'] or 'No skills'}</p>
        <p><strong>Location:</strong> {p['district']}{', ' + p['village'] if p['village'] else ''}</p>
        <p><strong>Bio:</strong> {p['bio'] or 'No bio'}</p>
        <p><strong>Status:</strong> <span class="badge badge-{p['status'].lower().replace(' ', '-')}">{p['status']}</span></p>
        <a href="{whatsapp_link(p['phone'])}" target="_blank" class="btn btn-whatsapp">Contact on WhatsApp</a>
    </div>
    """
    return render_page(p['name'], content)

# ============================================================
# JOB ROUTES
# ============================================================
@app.route('/jobs')
def list_jobs():
    db = get_db()
    jobs = db.execute("""
        SELECT j.id, j.title, j.company, j.description, j.location, j.status, j.posted_date
        FROM jobs j WHERE j.status='Open'
        ORDER BY j.featured DESC, j.id DESC
    """).fetchall()
    
    jobs_html = ""
    for j in jobs:
        jobs_html += f"""
        <div class="job-card">
            <div class="job-info">
                <h3>{j['title']} <span class="badge badge-open">Open</span></h3>
                <p>{j['company'] or 'Individual'} · {j['location'] or 'Uganda'} · {j['posted_date'][:10] if j['posted_date'] else ''}</p>
                <p>{j['description'][:150] if j['description'] else ''}</p>
                <a href="/job/{j['id']}" class="btn btn-small">View Details</a>
            </div>
        </div>"""
    
    content = f"""
    <div class="card">
        <div class="card-header">Available Jobs</div>
        <div id="jobCards">{jobs_html}</div>
    </div>
    """
    return render_page("Jobs", content)

@app.route('/job/<int:job_id>')
def job_detail(job_id):
    db = get_db()
    j = db.execute("SELECT j.*, u.name, u.phone FROM jobs j JOIN users u ON j.employer_id = u.id WHERE j.id=?", (job_id,)).fetchone()
    if not j:
        return "Job not found", 404
    
    content = f"""
    <div class="card">
        <div class="card-header">{j['title']}</div>
        <p><strong>Employer:</strong> {j['name']}</p>
        <p><strong>Location:</strong> {j['location']}{', ' + j['village'] if j['village'] else ''}</p>
        <p><strong>Description:</strong></p>
        <p>{j['description'] or 'No description'}</p>
        <a href="{whatsapp_link(j['phone'])}" target="_blank" class="btn btn-whatsapp">Apply via WhatsApp</a>
    </div>
    """
    return render_page(j['title'], content)

@app.route('/post-job', methods=['GET', 'POST'])
@login_required
def post_job():
    if request.method == 'POST':
        title = request.form['title']
        company = request.form.get('company', '')
        description = request.form['description']
        location = request.form['location']
        village = request.form.get('village', '')
        contact = request.form.get('contact', '')
        
        db = get_db()
        db.execute("INSERT INTO jobs (employer_id, title, company, description, location, village, contact, status) VALUES (?,?,?,?,?,?,?,'Open')",
                   (session['user_id'], title, company, description, location, village, contact))
        db.commit()
        return redirect('/dashboard')
    
    content = """
    <div class="card">
        <div class="card-header">Post a Job</div>
        <form method="POST">
            <label>Job Title *</label>
            <input type="text" name="title" required>
            <label>Company Name</label>
            <input type="text" name="company">
            <label>Description *</label>
            <textarea name="description" rows="5" required></textarea>
            <label>Location *</label>
            <input type="text" name="location" required>
            <label>Village/Area</label>
            <input type="text" name="village">
            <label>Contact Info</label>
            <input type="text" name="contact">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Post Job</button>
        </form>
    </div>
    """
    return render_page("Post a Job", content)

@app.route('/edit-job/<int:job_id>', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=? AND employer_id=?", (job_id, session['user_id'])).fetchone()
    if not job:
        return "Job not found", 404
    
    if request.method == 'POST':
        title = request.form['title']
        company = request.form.get('company', '')
        description = request.form['description']
        location = request.form['location']
        village = request.form.get('village', '')
        contact = request.form.get('contact', '')
        status = request.form.get('status', 'Open')
        
        db.execute("UPDATE jobs SET title=?, company=?, description=?, location=?, village=?, contact=?, status=? WHERE id=?",
                   (title, company, description, location, village, contact, status, job_id))
        db.commit()
        return redirect('/dashboard')
    
    status_options = f"""
    <select name="status">
        <option value="Open" {"selected" if job['status']=='Open' else ""}>Open</option>
        <option value="Taken" {"selected" if job['status']=='Taken' else ""}>Taken</option>
        <option value="Closed" {"selected" if job['status']=='Closed' else ""}>Closed</option>
    </select>
    """
    
    content = f"""
    <div class="card">
        <div class="card-header">Edit Job</div>
        <form method="POST">
            <label>Job Title</label>
            <input type="text" name="title" value="{job['title']}" required>
            <label>Company Name</label>
            <input type="text" name="company" value="{job['company'] or ''}">
            <label>Description</label>
            <textarea name="description" rows="5" required>{job['description'] or ''}</textarea>
            <label>Location</label>
            <input type="text" name="location" value="{job['location'] or ''}" required>
            <label>Village/Area</label>
            <input type="text" name="village" value="{job['village'] or ''}">
            <label>Contact Info</label>
            <input type="text" name="contact" value="{job['contact'] or ''}">
            <label>Status</label>
            {status_options}
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Update Job</button>
        </form>
    </div>
    """
    return render_page("Edit Job", content)

# ============================================================
# BOOST SYSTEM
# ============================================================
@app.route('/boost')
@login_required
def boost_profile():
    content = """
    <div class="card">
        <div class="card-header">Boost Your Profile</div>
        <p>Get featured at the top of search results!</p>
        <div style="background: linear-gradient(135deg, rgba(245,175,25,0.1), rgba(26,115,232,0.1)); padding: 20px; border-radius: 16px; margin: 20px 0;">
            <h3>💰 Pricing</h3>
            <p>7 days: UGX 5,000 | 30 days: UGX 15,000</p>
        </div>
        <form method="POST" action="/boost-submit">
            <label>Select Plan</label>
            <select name="plan" required>
                <option value="7">7 Days - UGX 5,000</option>
                <option value="30">30 Days - UGX 15,000</option>
            </select>
            <label>Transaction ID</label>
            <input type="text" name="trans_id" required placeholder="MTN/Airtel transaction ID">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Submit Request</button>
        </form>
        <p style="margin-top: 15px;">Send payment to: MTN 0785686404 or Airtel 0751318876 (Rocky Peter Abayo)</p>
    </div>
    """
    return render_page("Boost Profile", content)

@app.route('/boost-submit', methods=['POST'])
@login_required
def boost_submit():
    trans_id = request.form['trans_id']
    plan = request.form['plan']
    db = get_db()
    db.execute("INSERT INTO boost_requests (user_id, transaction_id, plan, status, boost_type) VALUES (?,?,?,'pending','profile')",
               (session['user_id'], trans_id, plan))
    db.commit()
    content = """
    <div class="card" style="text-align: center;">
        <div class="card-header">Request Submitted</div>
        <p>Your boost request will be verified within 24 hours.</p>
        <a href="/dashboard" class="btn">Back to Dashboard</a>
    </div>
    """
    return render_page("Boost Submitted", content)

@app.route('/boost-job/<int:job_id>')
@login_required
def boost_job(job_id):
    db = get_db()
    job = db.execute("SELECT title FROM jobs WHERE id=? AND employer_id=?", (job_id, session['user_id'])).fetchone()
    if not job:
        return "Job not found", 404
    
    content = f"""
    <div class="card">
        <div class="card-header">Boost Job: {job['title']}</div>
        <form method="POST" action="/boost-job-submit/{job_id}">
            <label>Select Plan</label>
            <select name="plan" required>
                <option value="7">7 Days - UGX 5,000</option>
                <option value="30">30 Days - UGX 15,000</option>
            </select>
            <label>Transaction ID</label>
            <input type="text" name="trans_id" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Submit</button>
        </form>
    </div>
    """
    return render_page("Boost Job", content)

@app.route('/boost-job-submit/<int:job_id>', methods=['POST'])
@login_required
def boost_job_submit(job_id):
    trans_id = request.form['trans_id']
    plan = request.form['plan']
    db = get_db()
    db.execute("INSERT INTO boost_requests (user_id, transaction_id, plan, status, boost_type, item_id) VALUES (?,?,?,'pending','job',?)",
               (session['user_id'], trans_id, plan, job_id))
    db.commit()
    content = """
    <div class="card" style="text-align: center;">
        <div class="card-header">Job Boost Submitted</div>
        <p>Your request will be verified within 24 hours.</p>
        <a href="/dashboard" class="btn">Back</a>
    </div>
    """
    return render_page("Boost Submitted", content)

@app.route('/boost-vendor')
@login_required
def boost_vendor():
    content = """
    <div class="card">
        <div class="card-header">Boost Your Vendor Profile</div>
        <form method="POST" action="/boost-vendor-submit">
            <label>Select Plan</label>
            <select name="plan" required>
                <option value="7">7 Days - UGX 5,000</option>
                <option value="30">30 Days - UGX 15,000</option>
            </select>
            <label>Transaction ID</label>
            <input type="text" name="trans_id" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Submit</button>
        </form>
    </div>
    """
    return render_page("Boost Vendor", content)

@app.route('/boost-vendor-submit', methods=['POST'])
@login_required
def boost_vendor_submit():
    trans_id = request.form['trans_id']
    plan = request.form['plan']
    db = get_db()
    db.execute("INSERT INTO boost_requests (user_id, transaction_id, plan, status, boost_type, item_id) VALUES (?,?,?,'pending','vendor',0)",
               (session['user_id'], trans_id, plan))
    db.commit()
    content = """
    <div class="card" style="text-align: center;">
        <div class="card-header">Vendor Boost Submitted</div>
        <p>Your request will be verified within 24 hours.</p>
        <a href="/dashboard" class="btn">Back</a>
    </div>
    """
    return render_page("Boost Submitted", content)

# ============================================================
# PAYMENT SYSTEM (Integrated with Plans)
# ============================================================
@app.route('/plans')
def list_plans():
    db = get_db()
    plans = db.execute("SELECT * FROM plans WHERE is_active=1 AND is_public=1 ORDER BY price_ugx ASC").fetchall()
    
    plans_html = ""
    for p in plans:
        plans_html += f"""
        <div class="card" style="text-align: center;">
            <h3>{p['name']}</h3>
            <p style="font-size: 2rem; color: var(--primary); font-weight: bold;">UGX {p['price_ugx']:,}</p>
            <p>{p['duration_minutes']} minutes of internet access</p>
            <a href="/buy-plan/{p['id']}" class="btn">Buy Now</a>
        </div>
        """
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-wifi"></i> Internet Plans</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px;">
            {plans_html}
        </div>
    </div>
    """
    return render_page("Internet Plans", content)

@app.route('/buy-plan/<int:plan_id>', methods=['GET', 'POST'])
def buy_plan(plan_id):
    db = get_db()
    plan = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        return redirect('/plans')
    
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        session['pending_phone'] = phone
        session['pending_plan_id'] = plan_id
        return redirect(url_for('verify_payment'))
    
    content = f"""
    <div class="card">
        <div class="card-header">Buy {plan['name']} - UGX {plan['price_ugx']:,}</div>
        <form method="POST">
            <label>Your Phone Number</label>
            <input type="tel" name="phone" required placeholder="0751318876">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Continue to Payment</button>
        </form>
    </div>
    """
    return render_page("Buy Plan", content)

@app.route('/verify-payment', methods=['GET', 'POST'])
def verify_payment():
    phone = session.get('pending_phone', '')
    plan_id = session.get('pending_plan_id', 1)
    
    db = get_db()
    plan = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        return redirect('/plans')
    
    if request.method == 'POST':
        raw_sms = request.form['raw_sms'].strip()
        
        if 'TID' in raw_sms or 'SENT.TID' in raw_sms:
            parsed = parse_airtel_sms(raw_sms)
        else:
            parsed = parse_mtn_sms(raw_sms)
        
        if not parsed['tid']:
            return render_page("Verify Payment", f"""
            <div class="card"><div class="alert alert-error">Could not detect Transaction ID.</div>
            <form method="POST"><textarea name="raw_sms" rows="6" required></textarea><button type="submit" class="btn">Verify Again</button></form></div>
            """)
        
        if parsed['amount'] != plan['price_ugx']:
            return render_page("Verify Payment", f"""
            <div class="card"><div class="alert alert-error">Amount mismatch. Expected UGX {plan['price_ugx']:,}.</div>
            <form method="POST"><textarea name="raw_sms" rows="6" required></textarea><button type="submit" class="btn">Verify Again</button></form></div>
            """)
        
        # Check if transaction already used
        existing = db.execute("SELECT id FROM voucher_requests WHERE transaction_id=?", (parsed['tid'],)).fetchone()
        if existing:
            return render_page("Verify Payment", '<div class="card"><div class="alert alert-error">This transaction ID has already been used.</div><a href="/plans" class="btn">Back to Plans</a></div>')
        
        # Generate voucher
        code = generate_voucher_code()
        db.execute("INSERT INTO vouchers (code, plan_id, payment_method, phone_number) VALUES (?,?,'sms',?)", (code, plan_id, phone))
        db.execute("INSERT INTO voucher_requests (phone_number, plan_id, raw_sms, transaction_id, amount, recipient, payment_date, status, voucher_code) VALUES (?,?,?,?,?,?,?,'approved',?)",
                   (phone, plan_id, raw_sms, parsed['tid'], parsed['amount'], parsed.get('recipient_name', ''), parsed.get('date', ''), code))
        db.commit()
        
        session.pop('pending_phone', None)
        session.pop('pending_plan_id', None)
        
        return render_page("Payment Success", f"""
        <div class="card" style="text-align: center;">
            <div class="card-header">✅ Payment Successful!</div>
            <p>Your voucher code:</p>
            <div class="voucher-code" id="vc">{code}</div>
            <button class="copy-btn" onclick="navigator.clipboard.writeText('{code}')">Copy</button>
            <p style="margin-top: 20px;">Use this code to connect to the internet.</p>
            <a href="/" class="btn">Back to Home</a>
        </div>
        """)
    
    content = f"""
    <div class="card">
        <div class="card-header">Verify Payment</div>
        <p><strong>Plan:</strong> {plan['name']} - UGX {plan['price_ugx']:,}</p>
        <p>Send payment to:</p>
        <ul>
            <li><strong>MTN Mobile Money:</strong> 0785686404</li>
            <li><strong>Airtel Money:</strong> 0751318876</li>
            <li><strong>Name:</strong> RockabyTech</li>
        </ul>
        <hr>
        <form method="POST">
            <label>Paste the Full SMS Here</label>
            <textarea name="raw_sms" rows="8" required placeholder="You have sent UGX 1,000 to ROCKABYTECH..."></textarea>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Verify Payment</button>
        </form>
    </div>
    """
    return render_page("Verify Payment", content)

@app.route('/redeem', methods=['GET', 'POST'])
def redeem_voucher():
    if request.method == 'POST':
        code = request.form['code'].strip().upper()
        db = get_db()
        voucher = db.execute("SELECT * FROM vouchers WHERE code=? AND used=0", (code,)).fetchone()
        if voucher:
            db.execute("UPDATE vouchers SET used=1, used_at=CURRENT_TIMESTAMP WHERE id=?", (voucher['id'],))
            db.commit()
            return render_page("Voucher Redeemed", """
            <div class="card" style="text-align: center;">
                <div class="card-header">🎉 Success!</div>
                <p>Your voucher has been activated!</p>
                <a href="/" class="btn">Back to Home</a>
            </div>
            """)
        else:
            return render_page("Redeem Voucher", """
            <div class="card">
                <div class="alert alert-error">Invalid or already used voucher code.</div>
                <form method="POST">
                    <label>Enter Voucher Code</label>
                    <input type="text" name="code" placeholder="CONNECT-XXXX-XXXX-XXXX" required>
                    <button type="submit" class="btn">Redeem</button>
                </form>
            </div>
            """)
    
    content = """
    <div class="card">
        <div class="card-header">Redeem Voucher</div>
        <form method="POST">
            <label>Enter Your Voucher Code</label>
            <input type="text" name="code" placeholder="CONNECT-XXXX-XXXX-XXXX" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Redeem</button>
        </form>
        <p style="margin-top: 15px;"><a href="/plans">Don't have a voucher? Buy one here</a></p>
    </div>
    """
    return render_page("Redeem Voucher", content)

# ============================================================
# SEPARATE ADMIN PANEL (Not in User Dashboard)
# ============================================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect('/admin/dashboard')
        return render_page("Admin Login", '<div class="card"><div class="alert alert-error">Wrong password.</div><a href="/admin/login">Try again</a></div>')
    
    content = """
    <div class="card" style="max-width: 400px; margin: 0 auto;">
        <div class="card-header">Admin Login</div>
        <form method="POST">
            <label>Password</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Login</button>
        </form>
    </div>
    """
    return render_page("Admin Login", content)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_providers = db.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    total_vendors = db.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
    total_jobs = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    pending_boosts = db.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'").fetchone()[0]
    pending_payments = db.execute("SELECT COUNT(*) FROM voucher_requests WHERE status='pending'").fetchone()[0]
    
    # Pending boosts
    boosts = db.execute("""
        SELECT br.id, u.name, u.phone, br.transaction_id, br.plan, br.boost_type, br.request_date
        FROM boost_requests br JOIN users u ON br.user_id = u.id
        WHERE br.status='pending' ORDER BY br.request_date DESC
    """).fetchall()
    
    boosts_html = ""
    for b in boosts:
        boosts_html += f"""
        <tr>
            <td>{b['name']}<br><small>{b['phone']}</small></td>
            <td>{b['transaction_id']}</td>
            <td>{b['plan']} days</td>
            <td>{b['boost_type']}</td>
            <td>
                <a href="/admin/approve-boost/{b['id']}" class="btn btn-small btn-success">Approve</a>
                <a href="/admin/reject-boost/{b['id']}" class="btn btn-small btn-danger">Reject</a>
            </td>
        </tr>"""
    
    if not boosts_html:
        boosts_html = "<tr><td colspan='5'>No pending boost requests</td></tr>"
    
    # Pending payments
    payments = db.execute("""
        SELECT id, phone_number, amount, transaction_id, created_at
        FROM voucher_requests WHERE status='pending' ORDER BY created_at DESC
    """).fetchall()
    
    payments_html = ""
    for p in payments:
        payments_html += f"""
        <tr>
            <td>{p['phone_number']}</td>
            <td>UGX {p['amount']:,}</td>
            <td>{p['transaction_id']}</td>
            <td>
                <a href="/admin/approve-payment/{p['id']}" class="btn btn-small btn-success">Approve</a>
                <a href="/admin/reject-payment/{p['id']}" class="btn btn-small btn-danger">Reject</a>
            </td>
        </tr>"""
    
    if not payments_html:
        payments_html = "<tr><td colspan='4'>No pending payments</td></tr>"
    
    content = f"""
    <div class="card">
        <div class="card-header">📊 Platform Statistics</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
            <div class="stat-card"><h3>{total_users}</h3><small>Users</small></div>
            <div class="stat-card"><h3>{total_providers}</h3><small>Freelancers</small></div>
            <div class="stat-card"><h3>{total_vendors}</h3><small>Vendors</small></div>
            <div class="stat-card"><h3>{total_jobs}</h3><small>Jobs</small></div>
            <div class="stat-card"><h3>{pending_boosts}</h3><small>Pending Boosts</small></div>
            <div class="stat-card"><h3>{pending_payments}</h3><small>Pending Payments</small></div>
        </div>
    </div>
    
    <div class="card">
        <div class="card-header">⏳ Pending Boost Requests</div>
        <table style="width: 100%;">
            <thead><tr><th>User</th><th>Transaction</th><th>Plan</th><th>Type</th><th>Action</th></tr></thead>
            <tbody>{boosts_html}</tbody>
        </table>
    </div>
    
    <div class="card">
        <div class="card-header">💰 Pending Payments</div>
        <table style="width: 100%;">
            <thead><tr><th>Phone</th><th>Amount</th><th>Transaction ID</th><th>Action</th></tr></thead>
            <tbody>{payments_html}</tbody>
        </table>
    </div>
    
    <div class="card">
        <div class="card-header">🔧 Admin Actions</div>
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <a href="/admin/plans" class="btn btn-outline">Manage Plans</a>
            <a href="/admin/logout" class="btn btn-danger">Logout</a>
        </div>
    </div>
    """
    return render_page("Admin Dashboard", content)

@app.route('/admin/approve-boost/<int:bid>')
def approve_boost(bid):
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    db = get_db()
    boost = db.execute("SELECT user_id, plan, boost_type, item_id FROM boost_requests WHERE id=?", (bid,)).fetchone()
    if boost:
        days = int(boost['plan'])
        expiry = date.today() + timedelta(days=days)
        if boost['boost_type'] == 'profile':
            db.execute("UPDATE providers SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, boost['user_id']))
        elif boost['boost_type'] == 'job':
            db.execute("UPDATE jobs SET featured=1, featured_expiry=? WHERE id=?", (expiry, boost['item_id']))
        elif boost['boost_type'] == 'vendor':
            db.execute("UPDATE vendors SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, boost['user_id']))
        db.execute("UPDATE boost_requests SET status='approved' WHERE id=?", (bid,))
        db.commit()
    return redirect('/admin/dashboard')

@app.route('/admin/reject-boost/<int:bid>')
def reject_boost(bid):
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    db = get_db()
    db.execute("UPDATE boost_requests SET status='rejected' WHERE id=?", (bid,))
    db.commit()
    return redirect('/admin/dashboard')

@app.route('/admin/approve-payment/<int:pid>')
def approve_payment(pid):
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    db = get_db()
    payment = db.execute("SELECT * FROM voucher_requests WHERE id=?", (pid,)).fetchone()
    if payment:
        code = generate_voucher_code()
        db.execute("INSERT INTO vouchers (code, plan_id, payment_method, phone_number) VALUES (?,?,'sms',?)", (code, payment['plan_id'], payment['phone_number']))
        db.execute("UPDATE voucher_requests SET status='approved', voucher_code=? WHERE id=?", (code, pid))
        db.commit()
    return redirect('/admin/dashboard')

@app.route('/admin/reject-payment/<int:pid>')
def reject_payment(pid):
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    db = get_db()
    db.execute("UPDATE voucher_requests SET status='rejected' WHERE id=?", (pid,))
    db.commit()
    return redirect('/admin/dashboard')

@app.route('/admin/plans')
def admin_plans():
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    db = get_db()
    plans = db.execute("SELECT * FROM plans ORDER BY price_ugx ASC").fetchall()
    
    rows = ""
    for p in plans:
        rows += f"""
        <tr>
            <td>{p['name']}</td>
            <td>{p['duration_minutes']} min</td>
            <td>UGX {p['price_ugx']:,}</td>
            <td>{'Yes' if p['is_active'] else 'No'}</td>
            <td>
                <a href="/admin/plan/edit/{p['id']}" class="btn btn-small btn-outline">Edit</a>
                <a href="/admin/plan/delete/{p['id']}" class="btn btn-small btn-danger" onclick="return confirm('Delete?')">Delete</a>
            </td>
        </tr>"""
    
    content = f"""
    <div class="card">
        <div class="card-header">Manage Internet Plans</div>
        <a href="/admin/plan/add" class="btn btn-success" style="margin-bottom: 20px;">+ Add Plan</a>
        <table style="width: 100%;">
            <thead><tr><th>Name</th><th>Duration</th><th>Price</th><th>Active</th><th>Action</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        <a href="/admin/dashboard" class="btn btn-outline" style="margin-top: 20px;">Back to Dashboard</a>
    </div>
    """
    return render_page("Admin Plans", content)

@app.route('/admin/plan/add', methods=['GET', 'POST'])
def admin_add_plan():
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    if request.method == 'POST':
        name = request.form['name']
        duration = int(request.form['duration'])
        price = int(request.form['price'])
        db = get_db()
        db.execute("INSERT INTO plans (name, duration_minutes, price_ugx, is_public) VALUES (?,?,?,1)", (name, duration, price))
        db.commit()
        return redirect('/admin/plans')
    
    content = """
    <div class="card">
        <div class="card-header">Add New Plan</div>
        <form method="POST">
            <label>Plan Name</label>
            <input type="text" name="name" required>
            <label>Duration (minutes)</label>
            <input type="number" name="duration" required>
            <label>Price (UGX)</label>
            <input type="number" name="price" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Create Plan</button>
        </form>
    </div>
    """
    return render_page("Add Plan", content)

@app.route('/admin/plan/edit/<int:plan_id>', methods=['GET', 'POST'])
def admin_edit_plan(plan_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    db = get_db()
    plan = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        return redirect('/admin/plans')
    
    if request.method == 'POST':
        name = request.form['name']
        duration = int(request.form['duration'])
        price = int(request.form['price'])
        is_active = 1 if request.form.get('is_active') else 0
        db.execute("UPDATE plans SET name=?, duration_minutes=?, price_ugx=?, is_active=? WHERE id=?", (name, duration, price, is_active, plan_id))
        db.commit()
        return redirect('/admin/plans')
    
    content = f"""
    <div class="card">
        <div class="card-header">Edit Plan</div>
        <form method="POST">
            <label>Plan Name</label>
            <input type="text" name="name" value="{plan['name']}" required>
            <label>Duration (minutes)</label>
            <input type="number" name="duration" value="{plan['duration_minutes']}" required>
            <label>Price (UGX)</label>
            <input type="number" name="price" value="{plan['price_ugx']}" required>
            <label><input type="checkbox" name="is_active" {'checked' if plan['is_active'] else ''}> Active</label>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Update Plan</button>
        </form>
    </div>
    """
    return render_page("Edit Plan", content)

@app.route('/admin/plan/delete/<int:plan_id>')
def admin_delete_plan(plan_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    db = get_db()
    db.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    db.commit()
    return redirect('/admin/plans')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin/login')

    # ============================================================
# SEPARATE ADMIN PANEL
# ============================================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == 'Trythorous2909@1707#!':
            session['admin_logged_in'] = True
            return redirect('/admin/dashboard')
        return '<div class="alert alert-error">Wrong password. <a href="/admin/login">Try again</a></div>'
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login</title>
        <style>
            body { font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f4f8; }
            .card { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); width: 300px; }
            input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; }
            button { width: 100%; padding: 10px; background: #f5af19; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Admin Login</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="Enter admin password" required>
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    import sqlite3
    db = sqlite3.connect('rockabyconnect.db')
    db.row_factory = sqlite3.Row
    c = db.cursor()
    
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_providers = c.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    total_vendors = c.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
    total_jobs = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    pending_boosts = c.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'").fetchone()[0]
    
    boosts = c.execute("""
        SELECT br.id, u.name, u.phone, br.transaction_id, br.plan, br.boost_type
        FROM boost_requests br JOIN users u ON br.user_id = u.id
        WHERE br.status='pending' ORDER BY br.request_date DESC
    """).fetchall()
    
    db.close()
    
    boosts_html = ""
    for b in boosts:
        boosts_html += f'''
        <tr>
            <td>{b['name']}<br><small>{b['phone']}</small></td>
            <td>{b['transaction_id']}</td>
            <td>{b['plan']} days</td>
            <td>{b['boost_type']}</td>
            <td>
                <a href="/admin/approve-boost/{b['id']}" style="background:green; color:white; padding:4px 8px; text-decoration:none; border-radius:4px;">Approve</a>
                <a href="/admin/reject-boost/{b['id']}" style="background:red; color:white; padding:4px 8px; text-decoration:none; border-radius:4px;">Reject</a>
            </td>
        </tr>'''
    
    if not boosts_html:
        boosts_html = '<tr><td colspan="5">No pending boost requests</td></tr>'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body {{ font-family: Arial; background: #f0f4f8; margin: 0; padding: 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .card {{ background: white; border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px; }}
            .stat {{ background: linear-gradient(135deg, #f5af19, #e09e15); color: white; padding: 20px; border-radius: 12px; text-align: center; }}
            .stat h3 {{ font-size: 2rem; margin: 0; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background: #f5f5f5; }}
            .btn {{ display: inline-block; padding: 10px 20px; background: #f5af19; color: white; text-decoration: none; border-radius: 8px; margin-top: 20px; }}
            .btn-danger {{ background: #dc3545; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h2>Admin Dashboard</h2>
                <div class="stats">
                    <div class="stat"><h3>{total_users}</h3><p>Total Users</p></div>
                    <div class="stat"><h3>{total_providers}</h3><p>Freelancers</p></div>
                    <div class="stat"><h3>{total_vendors}</h3><p>Vendors</p></div>
                    <div class="stat"><h3>{total_jobs}</h3><p>Jobs</p></div>
                    <div class="stat"><h3>{pending_boosts}</h3><p>Pending Boosts</p></div>
                </div>
            </div>
            
            <div class="card">
                <h3>Pending Boost Requests</h3>
                <table>
                    <tr><th>User</th><th>Transaction</th><th>Plan</th><th>Type</th><th>Action</th></tr>
                    {boosts_html}
                </table>
                <a href="/admin/logout" class="btn btn-danger">Logout</a>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/admin/approve-boost/<int:bid>')
def admin_approve_boost(bid):
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    import sqlite3
    from datetime import date, timedelta
    
    db = sqlite3.connect('rockabyconnect.db')
    c = db.cursor()
    
    boost = c.execute("SELECT user_id, plan, boost_type, item_id FROM boost_requests WHERE id=?", (bid,)).fetchone()
    if boost:
        days = int(boost[1])
        expiry = date.today() + timedelta(days=days)
        if boost[2] == 'profile':
            c.execute("UPDATE providers SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, boost[0]))
        elif boost[2] == 'job':
            c.execute("UPDATE jobs SET featured=1, featured_expiry=? WHERE id=?", (expiry, boost[3]))
        elif boost[2] == 'vendor':
            c.execute("UPDATE vendors SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, boost[0]))
        c.execute("UPDATE boost_requests SET status='approved' WHERE id=?", (bid,))
        db.commit()
    
    db.close()
    return redirect('/admin/dashboard')

@app.route('/admin/reject-boost/<int:bid>')
def admin_reject_boost(bid):
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    
    import sqlite3
    db = sqlite3.connect('rockabyconnect.db')
    c = db.cursor()
    c.execute("UPDATE boost_requests SET status='rejected' WHERE id=?", (bid,))
    db.commit()
    db.close()
    return redirect('/admin/dashboard')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin/login')

# ============================================================
# RUN APP
# ============================================================
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
