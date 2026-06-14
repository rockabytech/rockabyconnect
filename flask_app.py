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

# Admin password for the admin panel
ADMIN_PASSWORD = 'Trythorous2909@1707#!'

# File upload settings
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# Skill suggestions for freelancers
SKILL_SUGGESTIONS = [
    'Plumbing', 'Electrical', 'Carpentry', 'Painting', 'Cleaning',
    'Tutoring', 'Graphic Design', 'Web Development', 'Tailoring',
    'Cooking', 'Driving', 'Bricklaying', 'Construction', 'Boda Rider',
    'Maid', 'Gardening', 'Security Guard', 'Welding', 'Salon/Hair dressing',
    'Farming', 'Other'
]

FREELANCER_STATUSES = ['Available', 'Occupied', 'On Leave']
VENDOR_STATUSES = ['Open', 'Closed', 'Away']

# Database path
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
    """Initialize all database tables"""
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
    
    # Providers (freelancers) table
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
    
    # Add missing columns to providers if needed
    c.execute("PRAGMA table_info(providers)")
    prov_cols = [col[1] for col in c.fetchall()]  # ✅ FIXED: use c.fetchall()
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
    
    # Add missing columns to vendors
    c.execute("PRAGMA table_info(vendors)")
    vend_cols = [col[1] for col in c.fetchall()]  # ✅ FIXED: use c.fetchall()
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
    
    # Add missing columns to jobs
    c.execute("PRAGMA table_info(jobs)")
    job_cols = [col[1] for col in c.fetchall()]  # ✅ FIXED: use c.fetchall()
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
    
    # Payment tables
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        plan_id INTEGER,
        payment_method TEXT DEFAULT 'sms',
        phone_number TEXT,
        used INTEGER DEFAULT 0,
        used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    # Check if plans exist, if not, add default ones
    c.execute("SELECT COUNT(*) FROM plans")
    plan_count = c.fetchone()[0]  # ✅ FIXED: use c.fetchone()
    if plan_count == 0:
        default_plans = [
            ('3 Hours', 180, 500),
            ('24 Hours', 1440, 1000),
            ('Weekly', 10080, 5000),
            ('Monthly', 43200, 20000),
            ('Free Trial', 5, 0)
        ]
        for name, mins, price in default_plans:
            c.execute("INSERT INTO plans (name, duration_minutes, price_ugx, is_public) VALUES (?,?,?,1)", 
                     (name, mins, price))
    
    # Insert default admin user if not exists
    c.execute("SELECT COUNT(*) FROM users WHERE phone='256751318876'")
    admin_exists = c.fetchone()[0]  # ✅ FIXED: use c.fetchone()
    if admin_exists == 0:
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
    """Resize and save image"""
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
# PAYMENT HELPERS (MTN/Airtel SMS Parsing + Yo! Payments)
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

def yo_charge(phone, amount, plan_name):
    """Process Yo! Payments - simplified for RockabyConnect"""
    # For now, return None to use manual SMS verification
    # You can add your Yo! Payments credentials here
    return None

# ============================================================
# GLASSMORPHISM BASE TEMPLATE
# ============================================================
base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>RockabyConnect – {title}</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#f5af19">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #f5af19;
            --primary-dark: #e09e15;
            --primary-light: #f7c35c;
            --secondary: #1a73e8;
            --bg: #f0f4f8;
            --card-bg: rgba(255, 255, 255, 0.85);
            --glass-border: rgba(255, 255, 255, 0.3);
            --text: #1a1a1a;
            --text-secondary: #666;
            --border: #e0e0e0;
            --radius: 20px;
            --shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
            --shadow-hover: 0 12px 48px rgba(0, 0, 0, 0.12);
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        body.dark-mode {
            --bg: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.85);
            --glass-border: rgba(255, 255, 255, 0.08);
            --text: #f1f5f9;
            --text-secondary: #94a3b8;
            --border: #334155;
            --shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(245, 175, 25, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 90% 80%, rgba(26, 115, 232, 0.08) 0%, transparent 50%);
            color: var(--text);
            min-height: 100vh;
            transition: var(--transition);
        }

        .navbar {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
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
            box-shadow: 0 4px 15px rgba(245, 175, 25, 0.3);
        }

        .logo-text {
            font-size: 1.3rem;
            font-weight: 800;
            line-height: 1.2;
        }
        .logo-text span { color: var(--primary); }
        .logo-sub {
            font-size: 0.7rem;
            color: var(--text-secondary);
            line-height: 1;
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
            font-weight: 500;
            padding: 8px 16px;
            border-radius: 12px;
            transition: var(--transition);
            font-size: 0.95rem;
        }
        .nav-links a:hover,
        .nav-links a.active {
            background: rgba(245, 175, 25, 0.15);
            color: var(--primary);
        }

        .theme-toggle {
            background: rgba(245, 175, 25, 0.1);
            border: 1px solid var(--glass-border);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 1.2rem;
            transition: var(--transition);
            color: var(--text);
        }
        .theme-toggle:hover {
            background: rgba(245, 175, 25, 0.2);
            transform: scale(1.05);
        }

        .hamburger {
            display: none;
            background: none;
            border: none;
            font-size: 1.8rem;
            cursor: pointer;
            color: var(--text);
        }

        .container {
            max-width: 1200px;
            margin: 24px auto;
            padding: 0 20px;
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: var(--radius);
            padding: 28px;
            margin-bottom: 24px;
            box-shadow: var(--shadow);
            border: 1px solid var(--glass-border);
            transition: var(--transition);
        }
        .card:hover {
            transform: translateY(-4px);
            box-shadow: var(--shadow-hover);
        }
        .card-header {
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--primary);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .hero {
            background: linear-gradient(135deg, rgba(245, 175, 25, 0.15), rgba(26, 115, 232, 0.15));
            backdrop-filter: blur(10px);
            border-radius: var(--radius);
            padding: 60px 40px;
            text-align: center;
            margin-bottom: 30px;
            border: 1px solid var(--glass-border);
        }
        .hero h1 {
            font-size: 2.5rem;
            margin-bottom: 15px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .hero p {
            font-size: 1.1rem;
            color: var(--text-secondary);
            margin-bottom: 25px;
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
            font-size: 0.95rem;
            transition: var(--transition);
            box-shadow: 0 4px 15px rgba(245, 175, 25, 0.3);
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(245, 175, 25, 0.4);
        }
        .btn-outline {
            background: transparent;
            border: 2px solid var(--primary);
            color: var(--primary);
            box-shadow: none;
        }
        .btn-outline:hover {
            background: rgba(245, 175, 25, 0.1);
        }
        .btn-whatsapp {
            background: linear-gradient(135deg, #25D366, #128C7E);
            box-shadow: 0 4px 15px rgba(37, 211, 102, 0.3);
        }
        .btn-small {
            padding: 6px 14px;
            font-size: 0.85rem;
        }
        .btn-danger {
            background: linear-gradient(135deg, #dc3545, #c82333);
        }
        .btn-success {
            background: linear-gradient(135deg, #28a745, #20c997);
        }

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
            padding: 28px 20px;
            text-align: center;
            border: 1px solid var(--glass-border);
            transition: var(--transition);
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: -30px;
            right: -30px;
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            opacity: 0.1;
            border-radius: 50%;
        }
        .stat-card h3 {
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 8px;
        }
        .stat-card small {
            color: var(--text-secondary);
            font-size: 0.9rem;
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
            backdrop-filter: blur(5px);
            color: var(--text);
            font-weight: 600;
            padding: 6px 18px;
            border-radius: 30px;
            font-size: 0.85rem;
            text-decoration: none;
            transition: var(--transition);
            border: 1px solid var(--glass-border);
        }
        .chip:hover {
            background: var(--primary);
            color: white;
            transform: translateY(-2px);
        }

        .provider-card, .job-card, .vendor-card {
            display: flex;
            align-items: center;
            gap: 20px;
            padding: 20px 0;
            border-bottom: 1px solid var(--border);
            transition: var(--transition);
        }
        .provider-card:last-child, .job-card:last-child, .vendor-card:last-child {
            border-bottom: none;
        }
        .provider-card:hover, .job-card:hover, .vendor-card:hover {
            background: rgba(245, 175, 25, 0.05);
            margin: 0 -10px;
            padding: 20px 10px;
            border-radius: 16px;
        }
        .provider-info, .job-info, .vendor-info { flex: 1; }

        .profile-pic {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            object-fit: cover;
            border: 3px solid var(--primary);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        .vendor-img {
            width: 100px;
            height: 100px;
            object-fit: cover;
            border-radius: 12px;
            border: 1px solid var(--glass-border);
        }

        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.7rem;
            font-weight: 600;
            margin-left: 8px;
            vertical-align: middle;
        }
        .badge-available { background: #28a745; }
        .badge-occupied { background: #ffc107; color: #333; }
        .badge-leave { background: #6c757d; }
        .badge-open { background: #17a2b8; }
        .badge-taken { background: #6f42c1; }
        .badge-closed { background: #dc3545; }

        .search-bar input {
            width: 100%;
            padding: 14px 20px;
            border-radius: 40px;
            border: 1px solid var(--border);
            background: var(--card-bg);
            color: var(--text);
            font-size: 1rem;
            transition: var(--transition);
        }
        .search-bar input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(245, 175, 25, 0.2);
        }

        label {
            display: block;
            margin-top: 18px;
            margin-bottom: 6px;
            font-weight: 600;
            color: var(--text);
        }
        input, textarea, select {
            width: 100%;
            padding: 12px 16px;
            border-radius: 12px;
            border: 1px solid var(--border);
            background: var(--card-bg);
            color: var(--text);
            font-size: 0.95rem;
            transition: var(--transition);
        }
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(245, 175, 25, 0.2);
        }

        .rating {
            color: var(--primary);
            font-size: 1.1rem;
            letter-spacing: 2px;
        }
        .review-card {
            border-left: 3px solid var(--primary);
            padding: 12px 16px;
            margin: 12px 0;
            background: rgba(245, 175, 25, 0.05);
            border-radius: 0 12px 12px 0;
        }

        .voucher-code {
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: 1px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: #fff;
            padding: 12px 18px;
            border-radius: 10px;
            display: inline-block;
            margin: 10px 0;
            font-family: monospace;
        }
        .copy-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            margin-left: 10px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            font-weight: 700;
            color: var(--primary);
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
            box-shadow: 0 8px 25px rgba(37, 211, 102, 0.4);
            z-index: 999;
            text-decoration: none;
            transition: var(--transition);
        }
        .whatsapp-float:hover { transform: scale(1.1); }

        footer {
            text-align: center;
            padding: 30px;
            color: var(--text-secondary);
            font-size: 0.85rem;
            border-top: 1px solid var(--border);
            margin-top: 40px;
        }

        .alert {
            padding: 14px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }
        .alert-success {
            background: rgba(40, 167, 69, 0.15);
            border: 1px solid rgba(40, 167, 69, 0.3);
            color: #28a745;
        }
        .alert-error {
            background: rgba(220, 53, 69, 0.15);
            border: 1px solid rgba(220, 53, 69, 0.3);
            color: #dc3545;
        }

        @media (max-width: 768px) {
            .navbar { padding: 12px 16px; }
            .nav-links {
                display: none;
                width: 100%;
                flex-direction: column;
                gap: 10px;
                padding-top: 15px;
            }
            .nav-links.open { display: flex; }
            .hamburger { display: block; }
            .hero h1 { font-size: 1.8rem; }
            .hero { padding: 40px 20px; }
            .provider-card, .job-card, .vendor-card {
                flex-direction: column;
                align-items: flex-start;
            }
            .stat-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
            .container { padding: 0 16px; }
            .card { padding: 20px; }
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .card, .hero, .stat-card {
            animation: fadeInUp 0.6s ease-out;
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
            {% if session.user_id %}
                <a href="/logout">Logout</a>
            {% else %}
                <a href="/login">Login</a>
                <a href="/signup">Sign Up</a>
            {% endif %}
            <button class="theme-toggle" onclick="toggleTheme()" title="Toggle Dark/Light Mode">🌓</button>
        </div>
    </nav>
    
    <div class="container">
        {content}
    </div>
    
    <footer>
        <p>&copy; 2025 RockabyTech – Connecting Skills, Building Uganda 🇺🇬</p>
        <p style="margin-top: 8px; font-size: 0.75rem;">Empowering local workers and businesses across Uganda</p>
    </footer>
    
    <a href="https://wa.me/256751318876?text=Hi%20RockabyConnect%20Support" target="_blank" class="whatsapp-float" title="Chat with Support on WhatsApp">💬</a>
    
    <script>
        function toggleMenu() {
            document.getElementById('navMenu').classList.toggle('open');
        }
        function toggleTheme() {
            document.body.classList.toggle('dark-mode');
            const theme = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
            localStorage.setItem('rockabyconnect-theme', theme);
        }
        const savedTheme = localStorage.getItem('rockabyconnect-theme');
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-mode');
        }
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js').catch(err => console.log('SW registration failed:', err));
            });
        }
    </script>
</body>
</html>
"""

def render_page(title, content, active_page=""):
    """Render a page with the glassmorphism template"""
    return base_template.replace("{title}", title).replace("{content}", content)

# ============================================================
# HOME ROUTE
# ============================================================
@app.route('/')
def home():
    db = get_db()
    provider_count = get_provider_count()
    open_jobs = get_open_jobs_count()
    
    # Get featured providers
    featured_providers = db.execute("""
        SELECT p.id, u.name, p.skills, p.district, p.village, p.profile_pic, p.status, p.featured, p.featured_expiry
        FROM providers p JOIN users u ON p.user_id = u.id
        WHERE p.featured = 1 AND (p.featured_expiry IS NULL OR p.featured_expiry >= date('now'))
        ORDER BY p.id DESC LIMIT 4
    """).fetchall()
    
    # Get featured jobs
    featured_jobs = db.execute("""
        SELECT j.id, j.title, j.company, j.location, j.status
        FROM jobs j
        WHERE j.status='Open' AND j.featured = 1 AND (j.featured_expiry IS NULL OR j.featured_expiry >= date('now'))
        ORDER BY j.id DESC LIMIT 4
    """).fetchall()
    
    featured_html = ""
    for p in featured_providers:
        img_url = f"/static/uploads/{p['profile_pic']}" if p['profile_pic'] else ""
        status_class = p['status'].lower().replace(' ', '-')
        featured_html += f"""
        <div class="provider-card">
            <img src="{img_url or 'https://placehold.co/80x80?text=👤'}" class="profile-pic" onerror="this.src='https://placehold.co/80x80?text=👤'">
            <div class="provider-info">
                <h3>{p['name']} <span class="badge badge-{status_class}">{p['status']}</span> <span class="badge" style="background:var(--primary);">⭐ FEATURED</span></h3>
                <p class="meta"><strong>{p['skills'] or 'No skills listed'}</strong> · {p['district'] or 'Uganda'}{', ' + p['village'] if p['village'] else ''}</p>
                <a href="/provider/{p['id']}" class="btn btn-small">View Profile →</a>
            </div>
        </div>
        """
    
    jobs_html = ""
    for j in featured_jobs:
        jobs_html += f"""
        <div class="job-card">
            <div class="job-info">
                <h3>{j['title']} <span class="badge badge-open">Open</span> <span class="badge" style="background:var(--primary);">🔥 FEATURED</span></h3>
                <p class="meta">{j['company'] or 'Individual Employer'} · {j['location'] or 'Uganda'}</p>
                <a href="/job/{j['id']}" class="btn btn-small">View Details →</a>
            </div>
        </div>
        """
    
    content = f"""
    <div class="hero">
        <h1>✨ Get Work Done – or Get Paid</h1>
        <p>Uganda's premier freelance marketplace. Connect with trusted skilled workers near you.</p>
        <div style="display: flex; gap: 15px; justify-content: center; flex-wrap: wrap;">
            <a href="/offer-skill" class="btn"><i class="fas fa-user-plus"></i> Offer Your Skill</a>
            <a href="/post-job" class="btn btn-outline"><i class="fas fa-briefcase"></i> Post a Job</a>
        </div>
        <div class="category-chips">
            <span style="color: var(--text-secondary);">Popular:</span>
            <a href="/list?search=Boda+Rider" class="chip">Boda Rider</a>
            <a href="/list?search=Maid" class="chip">Maid</a>
            <a href="/list?search=Plumbing" class="chip">Plumbing</a>
            <a href="/list?search=Electrical" class="chip">Electrical</a>
            <a href="/list?search=Carpentry" class="chip">Carpentry</a>
            <a href="/list?search=Cooking" class="chip">Cooking</a>
        </div>
    </div>
    
    <div class="stat-grid">
        <div class="stat-card">
            <h3>{provider_count}</h3>
            <small>Skilled Workers</small>
        </div>
        <div class="stat-card">
            <h3>{open_jobs}</h3>
            <small>Open Jobs</small>
        </div>
        <div class="stat-card">
            <h3>10K+</h3>
            <small>Monthly Visitors</small>
        </div>
    </div>
    """
    
    if featured_providers:
        content += f"""
        <div class="card">
            <div class="card-header">⭐ Featured Freelancers</div>
            {featured_html}
        </div>
        """
    
    if featured_jobs:
        content += f"""
        <div class="card">
            <div class="card-header">🔥 Featured Jobs</div>
            {jobs_html}
        </div>
        """
    
    content += """
    <div class="card">
        <div class="card-header">📖 How It Works</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
            <div style="text-align: center;">
                <div style="font-size: 2rem;">🔍</div>
                <h3>1. Find Skills</h3>
                <p>Browse verified workers in your area</p>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 2rem;">📝</div>
                <h3>2. Post a Job</h3>
                <p>Describe what you need done</p>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 2rem;">💬</div>
                <h3>3. Connect</h3>
                <p>Chat on WhatsApp and get it done!</p>
            </div>
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
            return render_page("Sign Up", """
            <div class="card"><div class="alert alert-error">All fields required.</div><a href="/signup">Try again</a></div>
            """)
        hashed = generate_password_hash(password)
        try:
            db = get_db()
            db.execute("INSERT INTO users (phone, name, password_hash) VALUES (?, ?, ?)", (phone, name, hashed))
            user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()
            add_notification(user_id, 'email', f'Welcome {name}! Your RockabyConnect account is ready.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return render_page("Sign Up", """
            <div class="card"><div class="alert alert-error">Phone number already registered.</div><a href="/login">Login</a></div>
            """)
    
    content = """
    <div class="card" style="max-width: 500px; margin: 0 auto;">
        <div class="card-header">📝 Create Your Free Account</div>
        <form method="POST">
            <label><i class="fas fa-user"></i> Full Name *</label>
            <input type="text" name="name" required placeholder="Enter your full name">
            <label><i class="fas fa-phone"></i> Phone Number *</label>
            <input type="tel" name="phone" required placeholder="e.g., 0751318876">
            <label><i class="fas fa-lock"></i> Password *</label>
            <input type="password" name="password" required placeholder="Create a password">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-user-plus"></i> Sign Up</button>
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
        else:
            return render_page("Login", """
            <div class="card" style="max-width: 500px; margin: 0 auto;">
                <div class="card-header">🔐 Login</div>
                <div class="alert alert-error">Invalid phone number or password.</div>
                <a href="/login" class="btn">Try again</a>
            </div>
            """)
    
    content = """
    <div class="card" style="max-width: 500px; margin: 0 auto;">
        <div class="card-header">🔐 Login to Your Account</div>
        <form method="POST">
            <label><i class="fas fa-phone"></i> Phone Number</label>
            <input type="tel" name="phone" required placeholder="Enter your registered phone number">
            <label><i class="fas fa-lock"></i> Password</label>
            <input type="password" name="password" required placeholder="Enter your password">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-sign-in-alt"></i> Login</button>
        </form>
        <p style="margin-top: 20px; text-align: center;">No account? <a href="/signup">Create Account</a></p>
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
    user_id = session['user_id']
    db = get_db()
    provider = db.execute("SELECT id FROM providers WHERE user_id=?", (user_id,)).fetchone()
    if provider:
        return redirect('/edit-profile')
    else:
        return redirect('/create-profile')

# ============================================================
# DASHBOARD
# ============================================================
@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    db = get_db()
    
    provider = db.execute("SELECT * FROM providers WHERE user_id=?", (user_id,)).fetchone()
    vendor = db.execute("SELECT * FROM vendors WHERE user_id=?", (user_id,)).fetchone()
    jobs = db.execute("SELECT id, title, status FROM jobs WHERE employer_id=? ORDER BY id DESC", (user_id,)).fetchall()
    
    # Check if user is admin
    user_phone = db.execute("SELECT phone FROM users WHERE id=?", (user_id,)).fetchone()['phone']
    is_admin = (user_phone == '256751318876')
    
    profile_section = ""
    if provider:
        status_class = provider['status'].lower().replace(' ', '-')
        profile_section = f"""
        <div class="card">
            <div class="card-header"><i class="fas fa-user-cog"></i> My Freelancer Profile</div>
            <p><strong><i class="fas fa-tools"></i> Skills:</strong> {provider['skills'] or 'Not set'}</p>
            <p><strong><i class="fas fa-map-marker-alt"></i> Location:</strong> {provider['district'] or 'Not set'}{', ' + provider['village'] if provider['village'] else ''}</p>
            <p><strong><i class="fas fa-clock"></i> Status:</strong> <span class="badge badge-{status_class}">{provider['status']}</span></p>
            <div style="display: flex; gap: 10px; margin-top: 15px;">
                <a href="/edit-profile" class="btn btn-small"><i class="fas fa-edit"></i> Edit Profile</a>
                <a href="/boost" class="btn btn-small" style="background: var(--primary-dark);"><i class="fas fa-rocket"></i> Boost Profile</a>
            </div>
        </div>
        """
    else:
        profile_section = """
        <div class="card">
            <p><i class="fas fa-info-circle"></i> You haven't created a freelancer profile yet.</p>
            <a href="/create-profile" class="btn"><i class="fas fa-plus"></i> Create Freelancer Profile</a>
        </div>
        """
    
    vendor_section = ""
    if vendor:
        vstatus_class = vendor['status'].lower()
        vendor_section = f"""
        <div class="card">
            <div class="card-header"><i class="fas fa-store"></i> My Vendor Profile</div>
            <p><strong>Business:</strong> {vendor['business_name']}</p>
            <p><strong>Location:</strong> {vendor['district'] or 'Not set'}{', ' + vendor['village'] if vendor['village'] else ''}</p>
            <p><strong>Status:</strong> <span class="badge badge-{vstatus_class}">{vendor['status']}</span></p>
            <div style="display: flex; gap: 10px; margin-top: 15px;">
                <a href="/edit-vendor-profile" class="btn btn-small"><i class="fas fa-edit"></i> Edit Vendor</a>
                <a href="/boost-vendor" class="btn btn-small" style="background: var(--primary-dark);"><i class="fas fa-rocket"></i> Boost Vendor</a>
            </div>
        </div>
        """
    else:
        vendor_section = """
        <div class="card">
            <p><i class="fas fa-info-circle"></i> You haven't created a vendor profile yet.</p>
            <a href="/create-vendor-profile" class="btn"><i class="fas fa-plus"></i> Create Vendor Profile</a>
        </div>
        """
    
    jobs_html = ""
    if jobs:
        for job in jobs:
            badge_class = 'open' if job['status'] == 'Open' else ('taken' if job['status'] == 'Taken' else 'closed')
            jobs_html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--border);">
                <span><i class="fas fa-briefcase"></i> {job['title']} <span class="badge badge-{badge_class}">{job['status']}</span></span>
                <div style="display: flex; gap: 8px;">
                    <a href="/edit-job/{job['id']}" class="btn btn-small btn-outline">Edit</a>
                    <a href="/boost-job/{job['id']}" class="btn btn-small" style="background: var(--primary-dark);">Boost</a>
                </div>
            </div>
            """
    else:
        jobs_html = "<p><i class='fas fa-inbox'></i> No jobs posted yet.</p>"
    
    admin_section = ""
    if is_admin:
        pending_boosts = get_pending_boosts_count()
        pending_payments = db.execute("SELECT COUNT(*) FROM voucher_requests WHERE status='pending'").fetchone()[0]
        admin_section = f"""
        <div class="card" style="border: 2px solid var(--primary);">
            <div class="card-header"><i class="fas fa-crown"></i> Admin Panel</div>
            <p><strong>Pending Boost Requests:</strong> {pending_boosts}</p>
            <p><strong>Pending Payments:</strong> {pending_payments}</p>
            <div style="display: flex; gap: 10px; margin-top: 15px;">
                <a href="/admin" class="btn btn-small"><i class="fas fa-tachometer-alt"></i> Admin Dashboard</a>
                <a href="/admin/payments" class="btn btn-small btn-outline"><i class="fas fa-money-bill-wave"></i> Manage Payments</a>
            </div>
        </div>
        """
    
    dashboard_content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-user"></i> Welcome, {session['user_name']}!</div>
        <p><i class="fas fa-chart-line"></i> Manage your freelance presence, vendor profile, and job postings from one place.</p>
    </div>
    {profile_section}
    {vendor_section}
    <div class="card">
        <div class="card-header"><i class="fas fa-briefcase"></i> My Job Postings</div>
        {jobs_html}
        <a href="/post-job" class="btn" style="margin-top: 15px;"><i class="fas fa-plus"></i> Post a New Job</a>
    </div>
    {admin_section}
    """
    return render_page("Dashboard", dashboard_content)

# ============================================================
# FREELANCER PROFILE (Create/Edit)
# ============================================================
@app.route('/create-profile', methods=['GET', 'POST'])
@login_required
def create_profile():
    user_id = session['user_id']
    db = get_db()
    existing = db.execute("SELECT id FROM providers WHERE user_id=?", (user_id,)).fetchone()
    if existing:
        return redirect('/edit-profile')
    
    if request.method == 'POST':
        skills = request.form['skills'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Available')
        file = request.files.get('profile_pic')
        filename = None
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800)
        db.execute("INSERT INTO providers (user_id, skills, district, village, bio, profile_pic, status) VALUES (?,?,?,?,?,?,?)",
                   (user_id, skills, district, village, bio, filename, status))
        db.commit()
        return redirect('/dashboard')
    
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in FREELANCER_STATUSES])
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-user-plus"></i> Create Your Freelancer Profile</div>
        <form method="POST" enctype="multipart/form-data">
            <label><i class="fas fa-tools"></i> Skills * (separate by commas)</label>
            <input type="text" name="skills" required placeholder="e.g., Plumbing, Boda Rider, Carpentry, Electrical">
            <p style="font-size: 0.8rem; color: var(--text-secondary);">Suggestions: {', '.join(SKILL_SUGGESTIONS[:8])}...</p>
            <label><i class="fas fa-map-marker-alt"></i> District/City *</label>
            <input type="text" name="district" required placeholder="e.g., Kampala, Wakiso, Jinja">
            <label><i class="fas fa-home"></i> Village/Area</label>
            <input type="text" name="village" placeholder="e.g., Ntinda, Makindye">
            <label><i class="fas fa-info-circle"></i> Short Bio</label>
            <textarea name="bio" rows="3" placeholder="Tell clients about your experience and expertise..."></textarea>
            <label><i class="fas fa-camera"></i> Profile Picture</label>
            <input type="file" name="profile_pic" accept="image/*">
            <label><i class="fas fa-clock"></i> Availability Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Create Profile</button>
        </form>
    </div>
    """
    return render_page("Create Profile", content)

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user_id = session['user_id']
    db = get_db()
    provider = db.execute("SELECT * FROM providers WHERE user_id=?", (user_id,)).fetchone()
    if not provider:
        return redirect('/create-profile')
    
    if request.method == 'POST':
        skills = request.form['skills'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Available')
        file = request.files.get('profile_pic')
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800)
            db.execute("UPDATE providers SET skills=?, district=?, village=?, bio=?, profile_pic=?, status=? WHERE user_id=?",
                       (skills, district, village, bio, filename, status, user_id))
        else:
            db.execute("UPDATE providers SET skills=?, district=?, village=?, bio=?, status=? WHERE user_id=?",
                       (skills, district, village, bio, status, user_id))
        db.commit()
        return redirect('/dashboard')
    
    status_options = ''.join([f'<option value="{s}" {"selected" if s==provider["status"] else ""}>{s}</option>' for s in FREELANCER_STATUSES])
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-user-edit"></i> Edit Your Freelancer Profile</div>
        <form method="POST" enctype="multipart/form-data">
            <label><i class="fas fa-tools"></i> Skills *</label>
            <input type="text" name="skills" value="{provider['skills'] or ''}" required>
            <label><i class="fas fa-map-marker-alt"></i> District/City *</label>
            <input type="text" name="district" value="{provider['district'] or ''}" required>
            <label><i class="fas fa-home"></i> Village/Area</label>
            <input type="text" name="village" value="{provider['village'] or ''}">
            <label><i class="fas fa-info-circle"></i> Bio</label>
            <textarea name="bio" rows="3">{provider['bio'] or ''}</textarea>
            <label><i class="fas fa-camera"></i> Profile Picture</label>
            <input type="file" name="profile_pic" accept="image/*">
            <p style="font-size: 0.8rem;">Current: {provider['profile_pic'] or 'No image'}</p>
            <label><i class="fas fa-clock"></i> Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Save Changes</button>
        </form>
    </div>
    """
    return render_page("Edit Profile", content)

# ============================================================
# VENDOR PROFILES (Create/Edit)
# ============================================================
@app.route('/create-vendor-profile', methods=['GET', 'POST'])
@login_required
def create_vendor_profile():
    user_id = session['user_id']
    db = get_db()
    existing = db.execute("SELECT id FROM vendors WHERE user_id=?", (user_id,)).fetchone()
    if existing:
        return redirect('/edit-vendor-profile')
    
    if request.method == 'POST':
        business_name = request.form['business_name'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        landmark = request.form.get('landmark', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Open')
        
        filenames = [None, None, None]
        for idx, field in enumerate(['vendor_image', 'vendor_image2', 'vendor_image3']):
            file = request.files.get(field)
            if file and allowed_file(file.filename):
                filenames[idx] = save_resized_image(file, max_width=800)
        
        db.execute("""INSERT INTO vendors 
                   (user_id, business_name, district, village, landmark, bio, vendor_image, vendor_image2, vendor_image3, status) 
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                   (user_id, business_name, district, village, landmark, bio, filenames[0], filenames[1], filenames[2], status))
        db.commit()
        return redirect('/dashboard')
    
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in VENDOR_STATUSES])
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-store"></i> Create Your Vendor Profile</div>
        <form method="POST" enctype="multipart/form-data">
            <label><i class="fas fa-building"></i> Business Name *</label>
            <input type="text" name="business_name" required placeholder="e.g., Mukwano Hardware">
            <label><i class="fas fa-map-marker-alt"></i> District/City *</label>
            <input type="text" name="district" required placeholder="e.g., Kampala">
            <label><i class="fas fa-home"></i> Village/Area</label>
            <input type="text" name="village" placeholder="e.g., Ntinda">
            <label><i class="fas fa-location-dot"></i> Landmark</label>
            <input type="text" name="landmark" placeholder="e.g., Opposite SDA Church">
            <label><i class="fas fa-info-circle"></i> Business Description</label>
            <textarea name="bio" rows="3" placeholder="Describe your products or services..."></textarea>
            <label><i class="fas fa-camera"></i> Main Shop Photo</label>
            <input type="file" name="vendor_image" accept="image/*">
            <label><i class="fas fa-images"></i> Additional Photos</label>
            <input type="file" name="vendor_image2" accept="image/*">
            <input type="file" name="vendor_image3" accept="image/*">
            <label><i class="fas fa-clock"></i> Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Create Vendor Profile</button>
        </form>
    </div>
    """
    return render_page("Create Vendor Profile", content)

@app.route('/edit-vendor-profile', methods=['GET', 'POST'])
@login_required
def edit_vendor_profile():
    user_id = session['user_id']
    db = get_db()
    vendor = db.execute("SELECT * FROM vendors WHERE user_id=?", (user_id,)).fetchone()
    if not vendor:
        return redirect('/create-vendor-profile')
    
    if request.method == 'POST':
        business_name = request.form['business_name'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        landmark = request.form.get('landmark', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Open')
        
        current_images = [vendor['vendor_image'], vendor['vendor_image2'], vendor['vendor_image3']]
        for idx, field in enumerate(['vendor_image', 'vendor_image2', 'vendor_image3']):
            file = request.files.get(field)
            if file and allowed_file(file.filename):
                current_images[idx] = save_resized_image(file, max_width=800)
        
        db.execute("""UPDATE vendors SET 
                   business_name=?, district=?, village=?, landmark=?, bio=?, 
                   vendor_image=?, vendor_image2=?, vendor_image3=?, status=? 
                   WHERE user_id=?""",
                   (business_name, district, village, landmark, bio, 
                    current_images[0], current_images[1], current_images[2], status, user_id))
        db.commit()
        return redirect('/dashboard')
    
    status_options = ''.join([f'<option value="{s}" {"selected" if s==vendor["status"] else ""}>{s}</option>' for s in VENDOR_STATUSES])
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-store"></i> Edit Your Vendor Profile</div>
        <form method="POST" enctype="multipart/form-data">
            <label><i class="fas fa-building"></i> Business Name *</label>
            <input type="text" name="business_name" value="{vendor['business_name'] or ''}" required>
            <label><i class="fas fa-map-marker-alt"></i> District/City *</label>
            <input type="text" name="district" value="{vendor['district'] or ''}" required>
            <label><i class="fas fa-home"></i> Village/Area</label>
            <input type="text" name="village" value="{vendor['village'] or ''}">
            <label><i class="fas fa-location-dot"></i> Landmark</label>
            <input type="text" name="landmark" value="{vendor['landmark'] or ''}">
            <label><i class="fas fa-info-circle"></i> Business Description</label>
            <textarea name="bio" rows="3">{vendor['bio'] or ''}</textarea>
            <label><i class="fas fa-camera"></i> Main Photo</label>
            <input type="file" name="vendor_image" accept="image/*">
            <label><i class="fas fa-images"></i> Additional Photos</label>
            <input type="file" name="vendor_image2" accept="image/*">
            <input type="file" name="vendor_image3" accept="image/*">
            <label><i class="fas fa-clock"></i> Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Save Changes</button>
        </form>
    </div>
    """
    return render_page("Edit Vendor Profile", content)

# ============================================================
# VENDOR LISTING & DETAIL
# ============================================================
@app.route('/vendors')
def list_vendors():
    logged_in = 'user_id' in session
    db = get_db()
    today = date.today().isoformat()
    db.execute("UPDATE vendors SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    db.commit()
    
    vendors = db.execute("""
        SELECT v.id, v.business_name, v.district, v.village, v.landmark, v.bio, v.vendor_image, v.status, v.featured, v.featured_expiry, u.phone
        FROM vendors v JOIN users u ON v.user_id = u.id
        ORDER BY CASE WHEN v.featured = 1 AND (v.featured_expiry IS NULL OR v.featured_expiry >= date('now')) THEN 0 ELSE 1 END, v.id DESC
    """).fetchall()
    
    cards = ""
    for v in vendors:
        status_class = v['status'].lower()
        img_url = f"/static/uploads/{v['vendor_image']}" if v['vendor_image'] else ""
        active_feat = is_featured_now(v['featured'], v['featured_expiry'])
        feat_badge = '<span class="badge" style="background: var(--primary);">⭐ FEATURED</span>' if active_feat else ''
        loc_display = f"{v['district']}{', ' + v['village'] if v['village'] else ''}{', ' + v['landmark'] if v['landmark'] else ''}"
        
        if logged_in:
            contact = f'<a href="{whatsapp_link(v["phone"])}" target="_blank" class="btn btn-whatsapp btn-small"><i class="fab fa-whatsapp"></i> WhatsApp</a>'
        else:
            contact = '<span style="color: var(--text-secondary);"><i class="fas fa-lock"></i> <a href="/login">Login to view contact</a></span>'
        
        cards += f"""
        <div class="vendor-card">
            <img src="{img_url or 'https://placehold.co/100x100?text=🏪'}" class="vendor-img" onerror="this.src='https://placehold.co/100x100?text=🏪'">
            <div class="vendor-info">
                <h3><a href="/vendor/{v['id']}" style="color: inherit; text-decoration: none;">{v['business_name']}</a> <span class="badge badge-{status_class}">{v['status']}</span> {feat_badge}</h3>
                <p class="meta"><i class="fas fa-map-marker-alt"></i> {loc_display}</p>
                <p>{v['bio'][:100] + '...' if v['bio'] and len(v['bio']) > 100 else v['bio'] or ''}</p>
                {contact}
            </div>
        </div>"""
    
    if not cards:
        cards = "<p style='text-align: center;'><i class='fas fa-store-slash'></i> No vendors registered yet.</p>"
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-store"></i> Local Vendors & Shops</div>
        <div class="search-bar"><input type="text" id="vendorSearch" placeholder="🔍 Search by business name, location, landmark..." onkeyup="filterVendors()"></div>
        <div id="vendorCards">{cards}</div>
    </div>
    <script>
        function filterVendors() {{
            const q = document.getElementById('vendorSearch').value.toLowerCase();
            document.querySelectorAll('.vendor-card').forEach(card => {{
                card.style.display = card.innerText.toLowerCase().includes(q) ? 'flex' : 'none';
            }});
        }}
    </script>
    """
    return render_page("Vendors", content)

@app.route('/vendor/<int:vendor_id>')
def vendor_detail(vendor_id):
    logged_in = 'user_id' in session
    db = get_db()
    v = db.execute("""
        SELECT v.*, u.phone, u.name FROM vendors v JOIN users u ON v.user_id = u.id WHERE v.id=?
    """, (vendor_id,)).fetchone()
    
    if not v:
        return "Vendor not found.", 404
    
    status_class = v['status'].lower()
    img_url = f"/static/uploads/{v['vendor_image']}" if v['vendor_image'] else ""
    active_feat = is_featured_now(v['featured'], v['featured_expiry'])
    feat = '<span class="badge" style="background: var(--primary);">⭐ FEATURED</span>' if active_feat else ''
    
    village_display = f", {v['village']}" if v['village'] else ""
    landmark_display = f", {v['landmark']}" if v['landmark'] else ""
    
    if logged_in:
        contact_display = f'<a href="{whatsapp_link(v["phone"])}" target="_blank" class="btn btn-whatsapp"><i class="fab fa-whatsapp"></i> Contact on WhatsApp</a>'
    else:
        contact_display = '<p><a href="/login">Login</a> to view contact details.</p>'
    
    extra_images = ""
    if v['vendor_image2'] or v['vendor_image3']:
        extra_images = '<div style="display: flex; gap: 10px; margin-top: 10px;">'
        if v['vendor_image2']:
            extra_images += f'<img src="/static/uploads/{v["vendor_image2"]}" style="width: 100px; height: 80px; object-fit: cover; border-radius: 8px;">'
        if v['vendor_image3']:
            extra_images += f'<img src="/static/uploads/{v["vendor_image3"]}" style="width: 100px; height: 80px; object-fit: cover; border-radius: 8px;">'
        extra_images += '</div>'
    
    content = f"""
    <div class="card">
        <div class="card-header">{v['business_name']} {feat}</div>
        <img src="{img_url or 'https://placehold.co/300x200?text=🏪'}" style="width: 100%; max-height: 300px; object-fit: cover; border-radius: 16px; margin-bottom: 20px;" onerror="this.src='https://placehold.co/300x200?text=🏪'">
        {extra_images}
        <p><strong><i class="fas fa-map-marker-alt"></i> Location:</strong> {v['district']}{village_display}{landmark_display}</p>
        <p><strong><i class="fas fa-info-circle"></i> Description:</strong> {v['bio'] or 'No description provided.'}</p>
        <p><strong><i class="fas fa-clock"></i> Status:</strong> <span class="badge badge-{status_class}">{v['status']}</span></p>
        <div style="margin-top: 20px;">{contact_display}</div>
    </div>
    """
    return render_page(v['business_name'], content)

# ============================================================
# FREELANCER LISTING & DETAIL
# ============================================================
@app.route('/list')
def list_providers():
    logged_in = 'user_id' in session
    db = get_db()
    today = date.today().isoformat()
    db.execute("UPDATE providers SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    db.commit()
    
    providers = db.execute("""
        SELECT p.id, u.name, p.skills, u.phone, p.district, p.village, p.bio, p.profile_pic, p.status, p.featured, p.featured_expiry
        FROM providers p JOIN users u ON p.user_id = u.id
        ORDER BY CASE WHEN p.featured = 1 AND (p.featured_expiry IS NULL OR p.featured_expiry >= date('now')) THEN 0 ELSE 1 END, p.id DESC
    """).fetchall()
    
    cards_html = ""
    for p in providers:
        status_class = p['status'].lower().replace(' ', '-')
        img_url = f"/static/uploads/{p['profile_pic']}" if p['profile_pic'] else ""
        active_featured = is_featured_now(p['featured'], p['featured_expiry'])
        feat = '<span class="badge" style="background: var(--primary);">⭐ FEATURED</span>' if active_featured else ''
        location_display = f"{p['district']}{', ' + p['village'] if p['village'] else ''}"
        
        if logged_in:
            phone_display = f'<p style="margin-top: 5px;"><i class="fas fa-phone"></i> {p["phone"]}</p>'
            wa_button = f'<a href="{whatsapp_link(p["phone"])}" target="_blank" class="btn btn-whatsapp btn-small"><i class="fab fa-whatsapp"></i> Chat on WhatsApp</a>'
        else:
            phone_display = '<p style="margin-top: 5px; color: var(--text-secondary);"><i class="fas fa-lock"></i> <a href="/login">Login to view contact</a></p>'
            wa_button = ''
        
        cards_html += f"""
        <div class="provider-card">
            <img src="{img_url or 'https://placehold.co/80x80?text=👤'}" class="profile-pic" onerror="this.src='https://placehold.co/80x80?text=👤'">
            <div class="provider-info">
                <h3><a href="/provider/{p['id']}" style="color: inherit; text-decoration: none;">{p['name']}</a> <span class="badge badge-{status_class}">{p['status']}</span> {feat}</h3>
                <p class="meta"><strong><i class="fas fa-tools"></i> {p['skills'] or 'No skills listed'}</strong> · <i class="fas fa-map-marker-alt"></i> {location_display}</p>
                <p>{p['bio'][:100] + '...' if p['bio'] and len(p['bio']) > 100 else p['bio'] or ''}</p>
                {phone_display}
                {wa_button}
            </div>
        </div>"""
    
    if not cards_html:
        cards_html = "<p style='text-align: center;'><i class='fas fa-users-slash'></i> No freelancers registered yet.</p>"
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-users"></i> Find Skilled Workers</div>
        <div class="search-bar"><input type="text" id="searchInput" placeholder="🔍 Filter by name, skill, district, village..." onkeyup="filterCards()"></div>
        <div id="providerCards">{cards_html}</div>
    </div>
    <script>
        function filterCards() {{
            const q = document.getElementById('searchInput').value.toLowerCase();
            document.querySelectorAll('.provider-card').forEach(card => {{
                card.style.display = card.innerText.toLowerCase().includes(q) ? 'flex' : 'none';
            }});
        }}
    </script>
    """
    return render_page("Find Freelancers", content)

@app.route('/provider/<int:provider_id>')
def provider_detail(provider_id):
    logged_in = 'user_id' in session
    db = get_db()
    p = db.execute("""
        SELECT p.*, u.name, u.phone FROM providers p JOIN users u ON p.user_id = u.id WHERE p.id=?
    """, (provider_id,)).fetchone()
    
    if not p:
        return "Provider not found.", 404
    
    status_class = p['status'].lower().replace(' ', '-')
    img_url = f"/static/uploads/{p['profile_pic']}" if p['profile_pic'] else ""
    active_featured = is_featured_now(p['featured'], p['featured_expiry'])
    feat = '<span class="badge" style="background: var(--primary);">⭐ FEATURED</span>' if active_featured else ''
    village_display = f", {p['village']}" if p['village'] else ""
    
    if logged_in:
        contact_display = f'<a href="{whatsapp_link(p["phone"])}" target="_blank" class="btn btn-whatsapp"><i class="fab fa-whatsapp"></i> Contact on WhatsApp</a>'
    else:
        contact_display = '<p><a href="/login">Login</a> to view contact details.</p>'
    
    # Get reviews
    reviews = db.execute("""
        SELECT u.name, r.rating, r.comment, r.created_at FROM reviews r JOIN users u ON r.reviewer_id = u.id
        WHERE r.provider_id=? ORDER BY r.created_at DESC
    """, (provider_id,)).fetchall()
    
    avg_rating = db.execute("SELECT AVG(rating) as avg, COUNT(*) as cnt FROM reviews WHERE provider_id=?", (provider_id,)).fetchone()
    avg_rating_value = round(avg_rating['avg'], 1) if avg_rating['avg'] else 0
    
    reviews_html = ""
    for rev in reviews:
        reviews_html += f"""
        <div class="review-card">
            <strong><i class="fas fa-user"></i> {rev['name']}</strong> - <span class="rating">{'★'*rev['rating']}{'☆'*(5-rev['rating'])}</span>
            <br><small><i class="fas fa-calendar"></i> {rev['created_at'][:10]}</small>
            <p>{rev['comment']}</p>
        </div>"""
    
    if not reviews:
        reviews_html = "<p><i class='fas fa-comment-slash'></i> No reviews yet.</p>"
    
    review_form = ""
    if logged_in:
        existing = db.execute("SELECT id FROM reviews WHERE provider_id=? AND reviewer_id=?", (provider_id, session['user_id'])).fetchone()
        if not existing:
            review_form = f"""
            <hr>
            <h4><i class="fas fa-star"></i> Leave a Review</h4>
            <form method="POST" action="/review/{provider_id}">
                <label>Rating</label>
                <select name="rating" required>
                    <option value="">Select rating</option>
                    <option value="5">★★★★★ (5) - Excellent</option>
                    <option value="4">★★★★☆ (4) - Good</option>
                    <option value="3">★★★☆☆ (3) - Average</option>
                    <option value="2">★★☆☆☆ (2) - Poor</option>
                    <option value="1">★☆☆☆☆ (1) - Terrible</option>
                </select>
                <label>Comment</label>
                <textarea name="comment" rows="3" placeholder="Share your experience with this freelancer..."></textarea>
                <button type="submit" class="btn" style="margin-top: 10px;"><i class="fas fa-paper-plane"></i> Submit Review</button>
            </form>
            """
    else:
        review_form = "<p><a href='/login'>Login</a> to leave a review.</p>"
    
    content = f"""
    <div class="card">
        <div class="card-header">{p['name']} {feat}</div>
        <img src="{img_url or 'https://placehold.co/120x120?text=👤'}" class="profile-pic" style="width: 120px; height: 120px; margin-bottom: 20px;" onerror="this.src='https://placehold.co/120x120?text=👤'">
        <p><strong><i class="fas fa-tools"></i> Skills:</strong> {p['skills'] or 'No skills listed'}</p>
        <p><strong><i class="fas fa-map-marker-alt"></i> Location:</strong> {p['district']}{village_display}</p>
        <p><strong><i class="fas fa-info-circle"></i> Bio:</strong> {p['bio'] or 'No bio provided.'}</p>
        <p><strong><i class="fas fa-clock"></i> Status:</strong> <span class="badge badge-{status_class}">{p['status']}</span></p>
        <div style="margin-top: 20px;">{contact_display}</div>
    </div>
    
    <div class="card">
        <div class="card-header"><i class="fas fa-star"></i> Reviews ({avg_rating_value}/5)</div>
        {reviews_html}
        {review_form}
    </div>
    """
    return render_page(p['name'], content)

@app.route('/review/<int:provider_id>', methods=['POST'])
@login_required
def add_review(provider_id):
    rating = int(request.form['rating'])
    comment = request.form.get('comment', '')
    db = get_db()
    db.execute("INSERT INTO reviews (provider_id, reviewer_id, rating, comment) VALUES (?,?,?,?)",
               (provider_id, session['user_id'], rating, comment))
    db.commit()
    add_notification(provider_id, 'review', f'You received a {rating}-star review!')
    return redirect(f'/provider/{provider_id}')

# ============================================================
# JOB ROUTES
# ============================================================
@app.route('/jobs')
def list_jobs():
    db = get_db()
    today = date.today().isoformat()
    db.execute("UPDATE jobs SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    db.commit()
    
    jobs = db.execute("""
        SELECT j.id, j.title, j.company, j.description, j.location, j.village, j.contact, j.status, j.posted_date, j.job_image, j.featured, j.featured_expiry
        FROM jobs j
        WHERE j.status='Open'
        ORDER BY CASE WHEN j.featured = 1 AND (j.featured_expiry IS NULL OR j.featured_expiry >= date('now')) THEN 0 ELSE 1 END, j.id DESC
    """).fetchall()
    
    jobs_html = ""
    for j in jobs:
        badge_class = 'open' if j['status'] == 'Open' else ('taken' if j['status'] == 'Taken' else 'closed')
        active_feat = is_featured_now(j['featured'], j['featured_expiry'])
        feat_badge = '<span class="badge" style="background: var(--primary);">🔥 FEATURED</span>' if active_feat else ''
        location_display = f"{j['location']}{', ' + j['village'] if j['village'] else ''}"
        img_url = f"/static/uploads/{j['job_image']}" if j['job_image'] else ""
        
        jobs_html += f"""
        <div class="job-card">
            <img src="{img_url or 'https://placehold.co/80x80?text=💼'}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 12px;" onerror="this.src='https://placehold.co/80x80?text=💼'">
            <div class="job-info">
                <h3>{j['title']} <span class="badge badge-{badge_class}">{j['status']}</span> {feat_badge}</h3>
                <p class="meta"><i class="fas fa-building"></i> {j['company'] or 'Individual Employer'} · <i class="fas fa-map-marker-alt"></i> {location_display} · <i class="fas fa-calendar"></i> {j['posted_date'][:10] if j['posted_date'] else ''}</p>
                <p>{j['description'][:150] + '...' if j['description'] and len(j['description']) > 150 else j['description'] or ''}</p>
                <a href="/job/{j['id']}" class="btn btn-small">View Details →</a>
            </div>
        </div>"""
    
    if not jobs_html:
        jobs_html = "<p style='text-align: center;'><i class='fas fa-inbox'></i> No open jobs at the moment.</p>"
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-briefcase"></i> Available Jobs</div>
        <div class="search-bar"><input type="text" id="jobSearch" placeholder="🔍 Search by title, location..." onkeyup="filterJobs()"></div>
        <div id="jobCards">{jobs_html}</div>
    </div>
    <script>
        function filterJobs() {{
            const q = document.getElementById('jobSearch').value.toLowerCase();
            document.querySelectorAll('.job-card').forEach(card => {{
                card.style.display = card.innerText.toLowerCase().includes(q) ? 'flex' : 'none';
            }});
        }}
    </script>
    """
    return render_page("Jobs", content)

@app.route('/job/<int:job_id>')
def job_detail(job_id):
    db = get_db()
    j = db.execute("""
        SELECT j.*, u.name, u.phone FROM jobs j JOIN users u ON j.employer_id = u.id WHERE j.id=?
    """, (job_id,)).fetchone()
    
    if not j:
        return "Job not found.", 404
    
    badge_class = 'open' if j['status'] == 'Open' else ('taken' if j['status'] == 'Taken' else 'closed')
    location_display = f"{j['location']}{', ' + j['village'] if j['village'] else ''}"
    img_url = f"/static/uploads/{j['job_image']}" if j['job_image'] else ""
    
    contact_display = f'<a href="{whatsapp_link(j["phone"])}" target="_blank" class="btn btn-whatsapp"><i class="fab fa-whatsapp"></i> Apply via WhatsApp</a>'
    
    content = f"""
    <div class="card">
        <div class="card-header">{j['title']} <span class="badge badge-{badge_class}">{j['status']}</span></div>
        <img src="{img_url or 'https://placehold.co/300x200?text=💼'}" style="width: 100%; max-height: 300px; object-fit: cover; border-radius: 16px; margin-bottom: 20px;" onerror="this.src='https://placehold.co/300x200?text=💼'">
        <p><strong><i class="fas fa-building"></i> Employer:</strong> {j['name']}</p>
        <p><strong><i class="fas fa-building"></i> Company:</strong> {j['company'] or 'Individual'}</p>
        <p><strong><i class="fas fa-map-marker-alt"></i> Location:</strong> {location_display}</p>
        <p><strong><i class="fas fa-align-left"></i> Description:</strong></p>
        <p style="white-space: pre-wrap;">{j['description'] or 'No description provided.'}</p>
        <div style="margin-top: 20px;">{contact_display}</div>
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
        file = request.files.get('job_image')
        filename = None
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800)
        
        db = get_db()
        db.execute("""INSERT INTO jobs 
                   (employer_id, title, company, description, location, village, contact, status, job_image) 
                   VALUES (?,?,?,?,?,?,?,'Open',?)""",
                   (session['user_id'], title, company, description, location, village, contact, filename))
        db.commit()
        return redirect('/dashboard')
    
    content = """
    <div class="card">
        <div class="card-header"><i class="fas fa-plus-circle"></i> Post a New Job</div>
        <form method="POST" enctype="multipart/form-data">
            <label><i class="fas fa-briefcase"></i> Job Title *</label>
            <input type="text" name="title" required placeholder="e.g., Electrician Needed">
            <label><i class="fas fa-building"></i> Company Name (Optional)</label>
            <input type="text" name="company" placeholder="e.g., Mukwano Industries">
            <label><i class="fas fa-align-left"></i> Description *</label>
            <textarea name="description" rows="5" required placeholder="Describe the job requirements, duties, and any qualifications needed..."></textarea>
            <label><i class="fas fa-map-marker-alt"></i> District/City *</label>
            <input type="text" name="location" required placeholder="e.g., Kampala">
            <label><i class="fas fa-home"></i> Village/Area</label>
            <input type="text" name="village" placeholder="e.g., Ntinda">
            <label><i class="fas fa-phone"></i> Contact Info</label>
            <input type="text" name="contact" placeholder="Phone number or email for applicants">
            <label><i class="fas fa-camera"></i> Job Image (Optional)</label>
            <input type="file" name="job_image" accept="image/*">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-paper-plane"></i> Post Job</button>
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
        return "Job not found or unauthorized.", 404
    
    if request.method == 'POST':
        title = request.form['title']
        company = request.form.get('company', '')
        description = request.form['description']
        location = request.form['location']
        village = request.form.get('village', '')
        contact = request.form.get('contact', '')
        status = request.form.get('status', 'Open')
        file = request.files.get('job_image')
        filename = job['job_image']
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800)
        
        db.execute("""UPDATE jobs SET 
                   title=?, company=?, description=?, location=?, village=?, contact=?, status=?, job_image=? 
                   WHERE id=?""",
                   (title, company, description, location, village, contact, status, filename, job_id))
        db.commit()
        return redirect('/dashboard')
    
    status_options = f"""
    <label><i class="fas fa-clock"></i> Status</label>
    <select name="status">
        <option value="Open" {"selected" if job['status']=='Open' else ""}>Open</option>
        <option value="Taken" {"selected" if job['status']=='Taken' else ""}>Taken</option>
        <option value="Closed" {"selected" if job['status']=='Closed' else ""}>Closed</option>
    </select>
    """
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-edit"></i> Edit Job Posting</div>
        <form method="POST" enctype="multipart/form-data">
            <label><i class="fas fa-briefcase"></i> Job Title *</label>
            <input type="text" name="title" value="{job['title']}" required>
            <label><i class="fas fa-building"></i> Company Name</label>
            <input type="text" name="company" value="{job['company'] or ''}">
            <label><i class="fas fa-align-left"></i> Description *</label>
            <textarea name="description" rows="5" required>{job['description'] or ''}</textarea>
            <label><i class="fas fa-map-marker-alt"></i> District/City *</label>
            <input type="text" name="location" value="{job['location'] or ''}" required>
            <label><i class="fas fa-home"></i> Village/Area</label>
            <input type="text" name="village" value="{job['village'] or ''}">
            <label><i class="fas fa-phone"></i> Contact Info</label>
            <input type="text" name="contact" value="{job['contact'] or ''}">
            <label><i class="fas fa-camera"></i> Job Image</label>
            <input type="file" name="job_image" accept="image/*">
            {status_options}
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Update Job</button>
        </form>
    </div>
    """
    return render_page("Edit Job", content)

# ============================================================
# BOOST SYSTEM (Profile, Job, Vendor)
# ============================================================
@app.route('/boost')
@login_required
def boost_profile():
    user_id = session['user_id']
    db = get_db()
    provider = db.execute("SELECT id FROM providers WHERE user_id=?", (user_id,)).fetchone()
    if not provider:
        return redirect('/create-profile')
    
    content = """
    <div class="card">
        <div class="card-header"><i class="fas fa-rocket"></i> Boost Your Profile</div>
        <p>Get featured at the top of search results and attract more customers!</p>
        <div style="background: linear-gradient(135deg, rgba(245,175,25,0.1), rgba(26,115,232,0.1)); padding: 20px; border-radius: 16px; margin: 20px 0;">
            <h3>💰 Pricing</h3>
            <ul style="list-style: none; padding: 0;">
                <li>📅 7 days: <strong>UGX 5,000</strong></li>
                <li>📅 30 days: <strong>UGX 15,000</strong></li>
            </ul>
        </div>
        <hr>
        <p><strong>📱 How to pay:</strong></p>
        <ol style="margin-left: 20px;">
            <li>Send the amount to:<br>
                <strong>MTN Mobile Money: 0785686404</strong><br>
                <strong>Airtel: 0751318876</strong><br>
                <strong>Name: Rocky Peter Abayo</strong>
            </li>
            <li>Enter the Transaction ID from your Mobile Money confirmation below.</li>
        </ol>
        <form method="POST" action="/boost-submit" style="margin-top: 20px;">
            <label><i class="fas fa-calendar"></i> Select Plan</label>
            <select name="plan" required>
                <option value="7">7 Days - UGX 5,000</option>
                <option value="30">30 Days - UGX 15,000</option>
            </select>
            <label><i class="fas fa-receipt"></i> Mobile Money Transaction ID *</label>
            <input type="text" name="trans_id" required placeholder="e.g., MTN123456789">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-paper-plane"></i> Submit for Verification</button>
        </form>
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
    add_notification(session['user_id'], 'sms', f'Boost request received (ID {trans_id}). We will verify shortly.')
    
    content = """
    <div class="card" style="text-align: center;">
        <div class="card-header"><i class="fas fa-check-circle"></i> Boost Request Submitted</div>
        <p>Your boost request has been received and will be verified within 24 hours.</p>
        <a href="/dashboard" class="btn"><i class="fas fa-arrow-left"></i> Back to Dashboard</a>
    </div>
    """
    return render_page("Boost Submitted", content)

@app.route('/boost-job/<int:job_id>')
@login_required
def boost_job(job_id):
    db = get_db()
    job = db.execute("SELECT id, employer_id, title FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or job['employer_id'] != session['user_id']:
        return "Job not found or unauthorized.", 404
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-rocket"></i> Boost Job: {job['title']}</div>
        <p>Make your job listing stand out and get more applicants!</p>
        <div style="background: linear-gradient(135deg, rgba(245,175,25,0.1), rgba(26,115,232,0.1)); padding: 20px; border-radius: 16px; margin: 20px 0;">
            <h3>💰 Pricing</h3>
            <ul style="list-style: none; padding: 0;">
                <li>📅 7 days: <strong>UGX 5,000</strong></li>
                <li>📅 30 days: <strong>UGX 15,000</strong></li>
            </ul>
        </div>
        <hr>
        <p><strong>📱 How to pay:</strong></p>
        <ol style="margin-left: 20px;">
            <li>Send the amount to:<br>
                <strong>MTN Mobile Money: 0785686404</strong><br>
                <strong>Airtel: 0751318876</strong><br>
                <strong>Name: Rocky Peter Abayo</strong>
            </li>
            <li>Enter the Transaction ID from your Mobile Money confirmation below.</li>
        </ol>
        <form method="POST" action="/boost-job-submit/{job_id}" style="margin-top: 20px;">
            <label><i class="fas fa-calendar"></i> Select Plan</label>
            <select name="plan" required>
                <option value="7">7 Days - UGX 5,000</option>
                <option value="30">30 Days - UGX 15,000</option>
            </select>
            <label><i class="fas fa-receipt"></i> Mobile Money Transaction ID *</label>
            <input type="text" name="trans_id" required placeholder="e.g., MTN123456789">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-paper-plane"></i> Submit</button>
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
        <div class="card-header"><i class="fas fa-check-circle"></i> Job Boost Submitted</div>
        <p>Your job boost request has been received and will be verified within 24 hours.</p>
        <a href="/dashboard" class="btn"><i class="fas fa-arrow-left"></i> Back to Dashboard</a>
    </div>
    """
    return render_page("Boost Submitted", content)

@app.route('/boost-vendor')
@login_required
def boost_vendor():
    user_id = session['user_id']
    db = get_db()
    vendor = db.execute("SELECT id FROM vendors WHERE user_id=?", (user_id,)).fetchone()
    if not vendor:
        return redirect('/create-vendor-profile')
    
    content = """
    <div class="card">
        <div class="card-header"><i class="fas fa-rocket"></i> Boost Your Vendor Profile</div>
        <p>Get your shop at the top of the vendor list and attract more customers!</p>
        <div style="background: linear-gradient(135deg, rgba(245,175,25,0.1), rgba(26,115,232,0.1)); padding: 20px; border-radius: 16px; margin: 20px 0;">
            <h3>💰 Pricing</h3>
            <ul style="list-style: none; padding: 0;">
                <li>📅 7 days: <strong>UGX 5,000</strong></li>
                <li>📅 30 days: <strong>UGX 15,000</strong></li>
            </ul>
        </div>
        <hr>
        <p><strong>📱 How to pay:</strong></p>
        <ol style="margin-left: 20px;">
            <li>Send the amount to:<br>
                <strong>MTN Mobile Money: 0785686404</strong><br>
                <strong>Airtel: 0751318876</strong><br>
                <strong>Name: Rocky Peter Abayo</strong>
            </li>
            <li>Enter the Transaction ID from your Mobile Money confirmation below.</li>
        </ol>
        <form method="POST" action="/boost-vendor-submit" style="margin-top: 20px;">
            <label><i class="fas fa-calendar"></i> Select Plan</label>
            <select name="plan" required>
                <option value="7">7 Days - UGX 5,000</option>
                <option value="30">30 Days - UGX 15,000</option>
            </select>
            <label><i class="fas fa-receipt"></i> Mobile Money Transaction ID *</label>
            <input type="text" name="trans_id" required placeholder="e.g., MTN123456789">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-paper-plane"></i> Submit for Verification</button>
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
        <div class="card-header"><i class="fas fa-check-circle"></i> Vendor Boost Submitted</div>
        <p>Your vendor boost request has been received and will be verified within 24 hours.</p>
        <a href="/dashboard" class="btn"><i class="fas fa-arrow-left"></i> Back to Dashboard</a>
    </div>
    """
    return render_page("Boost Submitted", content)

# ============================================================
# ADMIN PANEL (Separate from User Dashboard)
# ============================================================
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin')
        else:
            content = """
            <div class="card" style="max-width: 400px; margin: 0 auto;">
                <div class="card-header"><i class="fas fa-lock"></i> Admin Login</div>
                <div class="alert alert-error">Wrong password!</div>
                <form method="POST">
                    <label><i class="fas fa-key"></i> Password</label>
                    <input type="password" name="password" required>
                    <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Login</button>
                </form>
            </div>
            """
            return render_page("Admin Login", content)
    
    if not session.get('admin'):
        content = """
        <div class="card" style="max-width: 400px; margin: 0 auto;">
            <div class="card-header"><i class="fas fa-lock"></i> Admin Login</div>
            <form method="POST">
                <label><i class="fas fa-key"></i> Password</label>
                <input type="password" name="password" required>
                <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Login</button>
            </form>
        </div>
        """
        return render_page("Admin Login", content)
    
    db = get_db()
    
    # Handle approve/reject
    action = request.args.get('action')
    req_id = request.args.get('req_id')
    if action == 'approve' and req_id:
        req_id = int(req_id)
        req = db.execute("SELECT user_id, plan, boost_type, item_id FROM boost_requests WHERE id=?", (req_id,)).fetchone()
        if req:
            user_id, plan, btype, item_id = req
            days = int(plan)
            expiry = date.today() + timedelta(days=days)
            if btype == 'profile':
                db.execute("UPDATE providers SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, user_id))
            elif btype == 'job':
                db.execute("UPDATE jobs SET featured=1, featured_expiry=? WHERE id=?", (expiry, item_id))
            elif btype == 'vendor':
                db.execute("UPDATE vendors SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, user_id))
            db.execute("UPDATE boost_requests SET status='approved' WHERE id=?", (req_id,))
            db.commit()
            add_notification(user_id, 'sms', 'Your boost has been approved and is now live!')
        return redirect('/admin')
    
    if action == 'reject' and req_id:
        db.execute("UPDATE boost_requests SET status='rejected' WHERE id=?", (int(req_id),))
        db.commit()
        return redirect('/admin')
    
    # Get stats
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_providers = db.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    total_vendors = db.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
    total_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE status='Open'").fetchone()[0]
    pending_boosts = db.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'").fetchone()[0]
    pending_payments = db.execute("SELECT COUNT(*) FROM voucher_requests WHERE status='pending'").fetchone()[0]
    
    # Get pending boost requests
    pending = db.execute("""
        SELECT br.id, u.phone, u.name, br.transaction_id, br.plan, br.boost_type, br.item_id, br.request_date
        FROM boost_requests br JOIN users u ON br.user_id = u.id
        WHERE br.status = 'pending' ORDER BY br.request_date DESC
    """).fetchall()
    
    rows = ""
    for req in pending:
        rows += f"""
        <tr>
            <td>{req['id']}</td>
            <td>{req['name']}<br><small>{req['phone']}</small></td>
            <td>{req['transaction_id']}</td>
            <td>{req['plan']} days</td>
            <td><span class="badge" style="background: var(--primary);">{req['boost_type']}</span></td>
            <td><small>{req['request_date'][:16] if req['request_date'] else ''}</small></td>
            <td>
                <a href="/admin?action=approve&req_id={req['id']}" class="btn btn-small" style="background: #28a745;">✓ Approve</a>
                <a href="/admin?action=reject&req_id={req['id']}" class="btn btn-small btn-danger">✗ Reject</a>
            </td>
        </tr>"""
    
    if not rows:
        rows = "<tr><td colspan='7' style='text-align: center;'>No pending boost requests.</td></tr>"
    
    # Get pending payment verifications
    payments = db.execute("""
        SELECT id, phone_number, amount, transaction_id, created_at
        FROM voucher_requests WHERE status='pending' ORDER BY created_at DESC LIMIT 20
    """).fetchall()
    
    payment_rows = ""
    for p in payments:
        payment_rows += f"""
        <tr>
            <td>{p['phone_number']}</td>
            <td>UGX {p['amount']:,}</td>
            <td>{p['transaction_id']}</td>
            <td><small>{p['created_at'][:16] if p['created_at'] else ''}</small></td>
            <td>
                <a href="/admin/approve-payment/{p['id']}" class="btn btn-small" style="background: #28a745;">Approve</a>
                <a href="/admin/reject-payment/{p['id']}" class="btn btn-small btn-danger">Reject</a>
            </td>
        </tr>"""
    
    if not payment_rows:
        payment_rows = "<tr><td colspan='5' style='text-align: center;'>No pending payments.</td></tr>"
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-chart-line"></i> Dashboard Statistics</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
            <div class="stat-card"><h3>{total_users}</h3><small>Total Users</small></div>
            <div class="stat-card"><h3>{total_providers}</h3><small>Freelancers</small></div>
            <div class="stat-card"><h3>{total_vendors}</h3><small>Vendors</small></div>
            <div class="stat-card"><h3>{total_jobs}</h3><small>Open Jobs</small></div>
            <div class="stat-card"><h3>{pending_boosts}</h3><small>Pending Boosts</small></div>
            <div class="stat-card"><h3>{pending_payments}</h3><small>Pending Payments</small></div>
        </div>
    </div>
    
    <div class="card">
        <div class="card-header"><i class="fas fa-clock"></i> Pending Boost Requests</div>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr><th>ID</th><th>User</th><th>Transaction</th><th>Plan</th><th>Type</th><th>Date</th><th>Action</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </div>
    
    <div class="card">
        <div class="card-header"><i class="fas fa-money-bill-wave"></i> Pending Payment Verifications</div>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr><th>Phone</th><th>Amount</th><th>Transaction ID</th><th>Date</th><th>Action</th></tr>
                </thead>
                <tbody>{payment_rows}</tbody>
            </table>
        </div>
    </div>
    
    <div style="margin-top: 20px; display: flex; gap: 10px;">
        <a href="/admin/plans" class="btn btn-outline"><i class="fas fa-box"></i> Manage Plans</a>
        <a href="/admin/logout" class="btn btn-small btn-danger"><i class="fas fa-sign-out-alt"></i> Logout</a>
    </div>
    """
    return render_page("Admin Dashboard", content)

@app.route('/admin/approve-payment/<int:pid>')
def approve_payment(pid):
    if not session.get('admin'):
        return redirect('/admin')
    
    db = get_db()
    payment = db.execute("SELECT * FROM voucher_requests WHERE id=?", (pid,)).fetchone()
    if payment:
        # Generate voucher
        code = generate_voucher_code()
        db.execute("INSERT INTO vouchers (code, plan_id, payment_method, phone_number) VALUES (?,?,'sms',?)",
                   (code, payment['plan_id'], payment['phone_number']))
        db.execute("UPDATE voucher_requests SET status='approved', voucher_code=? WHERE id=?", (code, pid))
        db.commit()
        add_notification(payment['phone_number'], 'payment', f'Your payment of UGX {payment["amount"]:,} has been approved. Voucher: {code}')
    
    return redirect('/admin')

@app.route('/admin/reject-payment/<int:pid>')
def reject_payment(pid):
    if not session.get('admin'):
        return redirect('/admin')
    
    db = get_db()
    db.execute("UPDATE voucher_requests SET status='rejected' WHERE id=?", (pid,))
    db.commit()
    return redirect('/admin')

@app.route('/admin/plans')
def admin_plans():
    if not session.get('admin'):
        return redirect('/admin')
    
    db = get_db()
    plans = db.execute("SELECT * FROM plans ORDER BY price_ugx ASC").fetchall()
    
    rows = ""
    for p in plans:
        rows += f"""
        <tr>
            <td>{p['name']}</td>
            <td>{p['duration_minutes']} min</td>
            <td>UGX {p['price_ugx']:,}</td>
            <td>{p['speed_down'] or '-'}/{p['speed_up'] or '-'}</td>
            <td>{'Yes' if p['is_active'] else 'No'}</td>
            <td>
                <a href="/admin/plan/edit/{p['id']}" class="btn btn-small btn-outline">Edit</a>
            </td>
        </tr>"""
    
    if not rows:
        rows = "<tr><td colspan='6'>No plans found.</td></tr>"
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-box"></i> Manage Plans</div>
        <a href="/admin/plan/add" class="btn btn-success" style="margin-bottom: 20px;"><i class="fas fa-plus"></i> Add Plan</a>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr><th>Name</th><th>Duration</th><th>Price</th><th>Speed</th><th>Active</th><th>Action</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        <div style="margin-top: 20px;">
            <a href="/admin" class="btn btn-outline"><i class="fas fa-arrow-left"></i> Back to Admin</a>
        </div>
    </div>
    """
    return render_page("Admin Plans", content)

@app.route('/admin/plan/add', methods=['GET', 'POST'])
def admin_add_plan():
    if not session.get('admin'):
        return redirect('/admin')
    
    if request.method == 'POST':
        name = request.form['name']
        duration_minutes = int(request.form['duration'])
        price_ugx = int(request.form['price'])
        speed_down = request.form.get('speed_down', '')
        speed_up = request.form.get('speed_up', '')
        
        db = get_db()
        db.execute("INSERT INTO plans (name, duration_minutes, price_ugx, is_public, speed_down, speed_up) VALUES (?,?,?,1,?,?)",
                   (name, duration_minutes, price_ugx, speed_down, speed_up))
        db.commit()
        return redirect('/admin/plans')
    
    content = """
    <div class="card">
        <div class="card-header"><i class="fas fa-plus"></i> Add New Plan</div>
        <form method="POST">
            <label><i class="fas fa-tag"></i> Plan Name *</label>
            <input type="text" name="name" required placeholder="e.g., Weekly Plan">
            <label><i class="fas fa-hourglass-half"></i> Duration (minutes) *</label>
            <input type="number" name="duration" required placeholder="e.g., 10080 for weekly">
            <label><i class="fas fa-money-bill-wave"></i> Price (UGX) *</label>
            <input type="number" name="price" required placeholder="e.g., 5000">
            <label><i class="fas fa-tachometer-alt"></i> Download Speed</label>
            <input type="text" name="speed_down" placeholder="e.g., 5M">
            <label><i class="fas fa-tachometer-alt"></i> Upload Speed</label>
            <input type="text" name="speed_up" placeholder="e.g., 2M">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Create Plan</button>
        </form>
        <div style="margin-top: 20px;">
            <a href="/admin/plans" class="btn btn-outline"><i class="fas fa-arrow-left"></i> Back</a>
        </div>
    </div>
    """
    return render_page("Add Plan", content)

@app.route('/admin/plan/edit/<int:plan_id>', methods=['GET', 'POST'])
def admin_edit_plan(plan_id):
    if not session.get('admin'):
        return redirect('/admin')
    
    db = get_db()
    plan = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        return "Plan not found", 404
    
    if request.method == 'POST':
        name = request.form['name']
        duration_minutes = int(request.form['duration'])
        price_ugx = int(request.form['price'])
        speed_down = request.form.get('speed_down', '')
        speed_up = request.form.get('speed_up', '')
        is_active = 1 if request.form.get('is_active') else 0
        
        db.execute("UPDATE plans SET name=?, duration_minutes=?, price_ugx=?, speed_down=?, speed_up=?, is_active=? WHERE id=?",
                   (name, duration_minutes, price_ugx, speed_down, speed_up, is_active, plan_id))
        db.commit()
        return redirect('/admin/plans')
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-edit"></i> Edit Plan: {plan['name']}</div>
        <form method="POST">
            <label><i class="fas fa-tag"></i> Plan Name *</label>
            <input type="text" name="name" value="{plan['name']}" required>
            <label><i class="fas fa-hourglass-half"></i> Duration (minutes) *</label>
            <input type="number" name="duration" value="{plan['duration_minutes']}" required>
            <label><i class="fas fa-money-bill-wave"></i> Price (UGX) *</label>
            <input type="number" name="price" value="{plan['price_ugx']}" required>
            <label><i class="fas fa-tachometer-alt"></i> Download Speed</label>
            <input type="text" name="speed_down" value="{plan['speed_down'] or ''}" placeholder="e.g., 5M">
            <label><i class="fas fa-tachometer-alt"></i> Upload Speed</label>
            <input type="text" name="speed_up" value="{plan['speed_up'] or ''}" placeholder="e.g., 2M">
            <label><input type="checkbox" name="is_active" {'checked' if plan['is_active'] else ''}> Active</label>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Update Plan</button>
        </form>
        <div style="margin-top: 20px;">
            <a href="/admin/plans" class="btn btn-outline"><i class="fas fa-arrow-left"></i> Back</a>
        </div>
    </div>
    """
    return render_page("Edit Plan", content)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin')

# ============================================================
# PAYMENT ROUTES (SMS Verification)
# ============================================================
@app.route('/payment', methods=['GET', 'POST'])
def payment_page():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        plan_id = request.form.get('plan_id', 1)
        session['pending_phone'] = phone
        session['pending_plan_id'] = plan_id
        return redirect(url_for('sms_verify'))
    
    db = get_db()
    plans = db.execute("SELECT id, name, price_ugx, duration_minutes FROM plans WHERE is_active=1 AND is_public=1 ORDER BY price_ugx ASC").fetchall()
    
    plan_options = ""
    for p in plans:
        plan_options += f'<option value="{p["id"]}">{p["name"]} – {p["duration_minutes"]} min – UGX {p["price_ugx"]:,}</option>'
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-money-bill-wave"></i> Buy Internet Access</div>
        <form method="POST">
            <label><i class="fas fa-phone"></i> Your Phone Number *</label>
            <input type="tel" name="phone" required placeholder="e.g., 0751318876">
            <label><i class="fas fa-box"></i> Select Plan *</label>
            <select name="plan_id" required>{plan_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-arrow-right"></i> Continue to Payment</button>
        </form>
    </div>
    """
    return render_page("Buy Internet", content)

@app.route('/sms-verify', methods=['GET', 'POST'])
def sms_verify():
    phone = session.get('pending_phone', '')
    plan_id = session.get('pending_plan_id', 1)
    
    db = get_db()
    plan = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        return redirect('/payment')
    
    if request.method == 'POST':
        raw_sms = request.form['raw_sms'].strip()
        
        # Parse SMS (MTN or Airtel)
        if 'TID' in raw_sms or 'SENT.TID' in raw_sms:
            parsed = parse_airtel_sms(raw_sms)
        else:
            parsed = parse_mtn_sms(raw_sms)
        
        error = None
        if not parsed['tid']:
            error = "Could not detect Transaction ID."
        elif not parsed['amount']:
            error = "Could not detect amount."
        elif parsed['amount'] != plan['price_ugx']:
            error = f"Amount mismatch. Expected UGX {plan['price_ugx']:,}, got UGX {parsed['amount']:,}."
        
        if error:
            return render_page("Verify Payment", f"""
            <div class="card">
                <div class="alert alert-error">{error}</div>
                <form method="POST">
                    <label>Paste Full SMS Here</label>
                    <textarea name="raw_sms" rows="6" required></textarea>
                    <button type="submit" class="btn" style="margin-top:20px;">Verify Again</button>
                </form>
            </div>
            """)
        
        # Check if transaction ID already used
        existing = db.execute("SELECT id FROM voucher_requests WHERE transaction_id=?", (parsed['tid'],)).fetchone()
        if existing:
            return render_page("Verify Payment", """
            <div class="card">
                <div class="alert alert-error">This Transaction ID has already been used.</div>
                <a href="/payment" class="btn">Back to Payment</a>
            </div>
            """)
        
        # Generate voucher and save
        code = generate_voucher_code()
        db.execute("INSERT INTO vouchers (code, plan_id, payment_method, phone_number) VALUES (?,?,'sms',?)",
                   (code, plan_id, phone))
        db.execute("""INSERT INTO voucher_requests 
                   (phone_number, plan_id, raw_sms, transaction_id, amount, recipient, payment_date, status, voucher_code) 
                   VALUES (?,?,?,?,?,?,?,'approved',?)""",
                   (phone, plan_id, raw_sms, parsed['tid'], parsed['amount'], 
                    f"{parsed.get('recipient_name', '')} {parsed.get('recipient_number', '')}".strip(),
                    parsed.get('date', ''), code))
        db.commit()
        
        # Clear session
        session.pop('pending_phone', None)
        session.pop('pending_plan_id', None)
        
        return render_page("Payment Success", f"""
        <div class="card" style="text-align:center;">
            <div class="card-header">✅ Payment Verified!</div>
            <p>Your voucher code:</p>
            <div class="voucher-code" id="vc">{code}</div>
            <button class="copy-btn" onclick="navigator.clipboard.writeText('{code}')">📋 Copy Code</button>
            <p style="margin-top:20px;">Use this voucher code to activate your access.</p>
            <a href="/redeem" class="btn">Redeem Voucher</a>
        </div>
        """)
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-phone"></i> Verify Payment</div>
        <p><strong>Plan:</strong> {plan['name']} – UGX {plan['price_ugx']:,}</p>
        <p>Send payment to:</p>
        <ul>
            <li><strong>MTN Mobile Money:</strong> 0785686404</li>
            <li><strong>Airtel Money:</strong> 0751318876</li>
            <li><strong>Name:</strong> RockabyTech</li>
        </ul>
        <hr>
        <form method="POST">
            <label><i class="fas fa-sms"></i> Paste the Full SMS from MTN/Airtel Here</label>
            <textarea name="raw_sms" rows="8" required placeholder="Example: You have sent UGX 1,000 to ROCKABYTECH..."></textarea>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-check-circle"></i> Verify Payment</button>
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
            return render_page("Voucher Redeemed", f"""
            <div class="card" style="text-align:center;">
                <div class="card-header">🎉 Success!</div>
                <p>Your voucher has been activated! You are now connected to the internet.</p>
                <div class="voucher-code">{code}</div>
                <a href="/" class="btn">Back to Home</a>
            </div>
            """)
        else:
            return render_page("Redeem Voucher", """
            <div class="card">
                <div class="alert alert-error">Invalid or already used voucher code.</div>
                <form method="POST">
                    <label><i class="fas fa-ticket-alt"></i> Enter Voucher Code</label>
                    <input type="text" name="code" placeholder="CONNECT-XXXX-XXXX-XXXX" required>
                    <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Redeem</button>
                </form>
            </div>
            """)
    
    content = """
    <div class="card">
        <div class="card-header"><i class="fas fa-ticket-alt"></i> Redeem Voucher</div>
        <form method="POST">
            <label>Enter Your Voucher Code</label>
            <input type="text" name="code" placeholder="CONNECT-XXXX-XXXX-XXXX" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-check"></i> Redeem</button>
        </form>
        <p style="margin-top: 15px;"><a href="/payment">Don't have a voucher? Buy one here →</a></p>
    </div>
    """
    return render_page("Redeem Voucher", content)

# ============================================================
# PWA ROUTES
# ============================================================
@app.route('/manifest.json')
def manifest():
    manifest_content = {
        "name": "RockabyConnect",
        "short_name": "RockabyConnect",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f5af19",
        "theme_color": "#f5af19",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }
    resp = make_response(json.dumps(manifest_content))
    resp.headers['Content-Type'] = 'application/json'
    return resp

@app.route('/service-worker.js')
def service_worker():
    sw_content = '''
const CACHE_NAME = 'rockabyconnect-v1';
const urlsToCache = ['/', '/static/icon-192.png', '/static/icon-512.png'];

self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache)));
});

self.addEventListener('fetch', event => {
    event.respondWith(caches.match(event.request).then(response => response || fetch(event.request)));
});
'''
    resp = make_response(sw_content)
    resp.headers['Content-Type'] = 'application/javascript'
    return resp

# ============================================================
# RUN APP
# ============================================================
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
