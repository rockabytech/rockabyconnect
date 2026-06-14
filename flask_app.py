import os, sqlite3, re, random, string, math
from datetime import date, timedelta, datetime
from collections import defaultdict
from flask import Flask, render_template_string, request, redirect, url_for, session, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from PIL import Image

app = Flask(__name__)
app.secret_key = 'rockabytech-secret-key-change-in-production-2025'

ADMIN_PASSWORD = 'Trythorous2909@1707#!'

# Fix for Render - use relative path
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

SKILL_SUGGESTIONS = [
    'Plumbing', 'Electrical', 'Carpentry', 'Painting', 'Cleaning',
    'Tutoring', 'Graphic Design', 'Web Development', 'Tailoring',
    'Cooking', 'Driving', 'Bricklaying', 'Construction', 'Boda Rider',
    'Maid', 'Gardening', 'Security Guard', 'Welding', 'Salon/Hair dressing',
    'Farming', 'Other'
]

FREELANCER_STATUSES = ['Available', 'Occupied', 'On Leave']
VENDOR_STATUSES = ['Open', 'Closed', 'Away']

# ------------------------------------------------------------
# DATABASE PATH - Fix for Render
# ------------------------------------------------------------
DB_PATH = os.path.join(os.getcwd(), 'rockabyconnect.db')

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

def save_resized_image(file, max_width=800):
    """Resize image to max_width (keeping aspect ratio), save with unique name. Returns filename."""
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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_phone_number(text):
    if not text:
        return False
    digits = ''.join(filter(str.isdigit, text))
    return (digits.startswith('07') and len(digits) == 10) or (digits.startswith('2567') and len(digits) == 12)

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

def add_notification(user_id, type, message):
    try:
        db = get_db()
        db.execute("INSERT INTO notifications (user_id, type, message) VALUES (?,?,?)", (user_id, type, message))
        db.commit()
    except Exception as e:
        print(f"Notification failed: {e}")

def init_db():
    db = get_db()
    
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )''')
    
    db.execute('''CREATE TABLE IF NOT EXISTS providers (
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
    
    db.execute('''CREATE TABLE IF NOT EXISTS vendors (
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
    
    db.execute('''CREATE TABLE IF NOT EXISTS jobs (
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
    
    db.execute('''CREATE TABLE IF NOT EXISTS boost_requests (
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
    
    db.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id INTEGER NOT NULL,
        reviewer_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(provider_id) REFERENCES providers(id),
        FOREIGN KEY(reviewer_id) REFERENCES users(id)
    )''')
    
    db.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    db.commit()

# ------------------------------------------------------------
# GLASSMORPHISM BASE TEMPLATE with Dark/Light Mode
# ------------------------------------------------------------
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

        /* CSS Variables for Light/Dark Mode */
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
            --primary: #f5af19;
            --primary-dark: #e09e15;
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

        /* Glassmorphism Navbar */
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
            transition: var(--transition);
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

        .logo-text span {
            color: var(--primary);
        }

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

        /* Container */
        .container {
            max-width: 1200px;
            margin: 24px auto;
            padding: 0 20px;
        }

        /* Glassmorphism Cards */
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
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

        /* Hero Section */
        .hero {
            background: linear-gradient(135deg, 
                rgba(245, 175, 25, 0.15), 
                rgba(26, 115, 232, 0.15));
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

        /* Buttons */
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
            transform: translateY(-2px);
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

        /* Stat Grid */
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

        .stat-card:hover {
            transform: translateY(-4px);
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

        /* Category Chips */
        .category-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
            justify-content: center;
        }

        .chip {
            background: rgba(245, 175, 25, 0.15);
            backdrop-filter: blur(5px);
            color: var(--primary);
            padding: 6px 18px;
            border-radius: 30px;
            font-size: 0.85rem;
            text-decoration: none;
            transition: var(--transition);
            border: 1px solid var(--glass-border);
        }

        .chip:hover {
            background: rgba(245, 175, 25, 0.3);
            transform: translateY(-2px);
        }

        /* Provider/Job/Vendor Cards */
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

        .provider-info, .job-info, .vendor-info {
            flex: 1;
        }

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

        /* Badges */
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

        /* Search Bar */
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

        /* Forms */
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

        /* Rating Stars */
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

        /* Table */
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

        /* WhatsApp Float Button */
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

        .whatsapp-float:hover {
            transform: scale(1.1);
        }

        /* Footer */
        footer {
            text-align: center;
            padding: 30px;
            color: var(--text-secondary);
            font-size: 0.85rem;
            border-top: 1px solid var(--border);
            margin-top: 40px;
        }

        /* Alert Messages */
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

        /* Mobile Responsive */
        @media (max-width: 768px) {
            .navbar {
                padding: 12px 16px;
            }
            
            .nav-links {
                display: none;
                width: 100%;
                flex-direction: column;
                gap: 10px;
                padding-top: 15px;
            }
            
            .nav-links.open {
                display: flex;
            }
            
            .hamburger {
                display: block;
            }
            
            .hero h1 {
                font-size: 1.8rem;
            }
            
            .hero {
                padding: 40px 20px;
            }
            
            .provider-card, .job-card, .vendor-card {
                flex-direction: column;
                align-items: flex-start;
            }
            
            .stat-grid {
                grid-template-columns: 1fr 1fr;
                gap: 12px;
            }
            
            .container {
                padding: 0 16px;
            }
            
            .card {
                padding: 20px;
            }
        }

        /* Animations */
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
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
            <a href="/" class="{{ 'active' if active_page == 'home' else '' }}"><i class="fas fa-home"></i> Home</a>
            {% if session.user_id %}
                <a href="/dashboard" class="{{ 'active' if active_page == 'dashboard' else '' }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a>
            {% endif %}
            <a href="/list" class="{{ 'active' if active_page == 'list' else '' }}"><i class="fas fa-search"></i> Find Skills</a>
            <a href="/jobs" class="{{ 'active' if active_page == 'jobs' else '' }}"><i class="fas fa-briefcase"></i> Jobs</a>
            <a href="/vendors" class="{{ 'active' if active_page == 'vendors' else '' }}"><i class="fas fa-store"></i> Vendors</a>
            {% if session.user_id %}
                <a href="/logout"><i class="fas fa-sign-out-alt"></i> Logout</a>
            {% else %}
                <a href="/login"><i class="fas fa-sign-in-alt"></i> Login</a>
                <a href="/signup"><i class="fas fa-user-plus"></i> Sign Up</a>
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
    
    <a href="https://wa.me/256751318876?text=Hi%20RockabyConnect%20Support" target="_blank" class="whatsapp-float" title="Chat with Support on WhatsApp">
        💬
    </a>
    
    <script>
        function toggleMenu() {
            document.getElementById('navMenu').classList.toggle('open');
        }
        
        function toggleTheme() {
            document.body.classList.toggle('dark-mode');
            const theme = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
            localStorage.setItem('rockabyconnect-theme', theme);
        }
        
        // Load saved theme
        const savedTheme = localStorage.getItem('rockabyconnect-theme');
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-mode');
        }
        
        // Service Worker for PWA
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js').catch(err => {
                    console.log('ServiceWorker registration failed: ', err);
                });
            });
        }
    </script>
</body>
</html>
"""

# ------------------------------------------------------------
# PAGE HELPERS
# ------------------------------------------------------------
def render_page(title, content, active_page=""):
    """Helper to render pages with the glassmorphism template"""
    page = base_template.replace("{title}", title).replace("{content}", content).replace("{active_page}", active_page)
    return page

# ------------------------------------------------------------
# HOME ROUTE
# ------------------------------------------------------------
@app.route('/')
def home():
    db = get_db()
    provider_count = db.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    open_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE status='Open'").fetchone()[0]
    
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
    
    # Build featured providers HTML
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
    
    # Build featured jobs HTML
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
    
    return render_page('Home', content, 'home')

# ------------------------------------------------------------
# AUTHENTICATION ROUTES
# ------------------------------------------------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        name = request.form['name'].strip()
        password = request.form['password']
        if not phone or not name or not password:
            return "All fields required. <a href='/signup'>Back</a>"
        hashed = generate_password_hash(password)
        try:
            db = get_db()
            db.execute("INSERT INTO users (phone, name, password_hash) VALUES (?, ?, ?)", (phone, name, hashed))
            user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()
            add_notification(user_id, 'email', f'Welcome {name}! Your RockabyConnect account is ready.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "Phone number already registered. <a href='/login'>Login</a>"
    
    content = """
    <div class="card" style="max-width: 500px; margin: 0 auto;">
        <div class="card-header">📝 Create Your Free Account</div>
        <form method="POST">
            <label><i class="fas fa-user"></i> Full Name *</label>
            <input type="text" name="name" required placeholder="Enter your full name">
            <label><i class="fas fa-phone"></i> Phone Number *</label>
            <input type="tel" name="phone" required placeholder="e.g., 0751318876 or 256751318876">
            <label><i class="fas fa-lock"></i> Password *</label>
            <input type="password" name="password" required placeholder="Create a password">
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-user-plus"></i> Sign Up</button>
        </form>
        <p style="margin-top: 20px; text-align: center;">Already have an account? <a href="/login">Login</a></p>
    </div>
    """
    return render_page('Sign Up', content, 'signup')

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
            return render_page('Login', """
            <div class="card" style="max-width: 500px; margin: 0 auto;">
                <div class="card-header">🔐 Login</div>
                <div class="alert alert-error">Invalid phone number or password.</div>
                <form method="POST">
                    <label><i class="fas fa-phone"></i> Phone Number</label>
                    <input type="tel" name="phone" required>
                    <label><i class="fas fa-lock"></i> Password</label>
                    <input type="password" name="password" required>
                    <button type="submit" class="btn" style="width: 100%; margin-top: 20px;">Login</button>
                </form>
                <p style="margin-top: 20px; text-align: center;">No account? <a href="/signup">Sign Up</a></p>
            </div>
            """, 'login')
    
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
    return render_page('Login', content, 'login')

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

# ------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------
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
        pending_boosts = db.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'").fetchone()[0]
        admin_section = f"""
        <div class="card" style="border: 2px solid var(--primary);">
            <div class="card-header"><i class="fas fa-crown"></i> Admin Panel</div>
            <p><strong>Pending Boost Requests:</strong> {pending_boosts}</p>
            <a href="/admin" class="btn btn-small"><i class="fas fa-tachometer-alt"></i> Go to Admin Dashboard</a>
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
    return render_page('Dashboard', dashboard_content, 'dashboard')

# ------------------------------------------------------------
# FREELANCER PROFILE (Create/Edit)
# ------------------------------------------------------------
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
    return render_page('Create Profile', content)

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
    return render_page('Edit Profile', content)

        # ------------------------------------------------------------
# VENDOR PROFILES (Create/Edit/View)
# ------------------------------------------------------------
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
        <form method="POST" enctype="multipart/form-data" id="vendorForm">
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
            <label><i class="fas fa-images"></i> Additional Photos (Optional)</label>
            <input type="file" name="vendor_image2" accept="image/*">
            <input type="file" name="vendor_image3" accept="image/*">
            <label><i class="fas fa-clock"></i> Status</label>
            <select name="status">{status_options}</select>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Create Vendor Profile</button>
        </form>
    </div>
    <script>
    document.getElementById('vendorForm').addEventListener('submit', function(e) {{
        const fileInputs = document.querySelectorAll('#vendorForm input[type=file]');
        const promises = [];
        fileInputs.forEach(input => {{
            if (input.files.length > 0 && input.files[0].size > 500 * 1024) {{
                e.preventDefault();
                const reader = new FileReader();
                reader.onload = function(ev) {{
                    const img = new Image();
                    img.onload = function() {{
                        const canvas = document.createElement('canvas');
                        const maxWidth = 800;
                        let width = img.width, height = img.height;
                        if (width > maxWidth) {{
                            height = Math.round((maxWidth / width) * height);
                            width = maxWidth;
                        }}
                        canvas.width = width;
                        canvas.height = height;
                        canvas.getContext('2d').drawImage(img, 0, 0, width, height);
                        canvas.toBlob(function(blob) {{
                            const resizedFile = new File([blob], input.files[0].name, {{ type: 'image/jpeg', lastModified: Date.now() }});
                            const dt = new DataTransfer();
                            dt.items.add(resizedFile);
                            input.files = dt.files;
                        }}, 'image/jpeg', 0.85);
                    }};
                    img.src = ev.target.result;
                }};
                reader.readAsDataURL(input.files[0]);
            }}
        }});
        if (promises.length > 0) {{
            e.preventDefault();
            Promise.all(promises).then(() => document.getElementById('vendorForm').submit());
        }}
    }});
    </script>
    """
    return render_page('Create Vendor Profile', content)

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
    return render_page('Edit Vendor Profile', content)

# ------------------------------------------------------------
# VENDOR LISTING & DETAIL
# ------------------------------------------------------------
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
    return render_page('Vendors', content, 'vendors')

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
        extra_images = '<div class="vendor-img-gallery" style="display: flex; gap: 10px; margin-top: 10px;">'
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
    return render_page(v['business_name'], content, 'vendors')

# ------------------------------------------------------------
# JOB ROUTES
# ------------------------------------------------------------
@app.route('/jobs')
def list_jobs():
    logged_in = 'user_id' in session
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
    return render_page('Jobs', content, 'jobs')

@app.route('/job/<int:job_id>')
def job_detail(job_id):
    logged_in = 'user_id' in session
    db = get_db()
    j = db.execute("""
        SELECT j.*, u.name, u.phone FROM jobs j JOIN users u ON j.employer_id = u.id WHERE j.id=?
    """, (job_id,)).fetchone()
    
    if not j:
        return "Job not found.", 404
    
    badge_class = 'open' if j['status'] == 'Open' else ('taken' if j['status'] == 'Taken' else 'closed')
    location_display = f"{j['location']}{', ' + j['village'] if j['village'] else ''}"
    img_url = f"/static/uploads/{j['job_image']}" if j['job_image'] else ""
    
    if logged_in:
        contact_display = f'<a href="{whatsapp_link(j["phone"])}" target="_blank" class="btn btn-whatsapp"><i class="fab fa-whatsapp"></i> Apply via WhatsApp</a>'
    else:
        contact_display = '<p><a href="/login">Login</a> to view contact details and apply.</p>'
    
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
    return render_page(j['title'], content, 'jobs')

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
    return render_page('Post a Job', content)

@app.route('/edit-job/<int:job_id>', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or job['employer_id'] != session['user_id']:
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
    return render_page('Edit Job', content)

# ------------------------------------------------------------
# FREELANCER LISTING & DETAIL
# ------------------------------------------------------------
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
    return render_page('Find Freelancers', content, 'list')

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
    
    avg_rating = db.execute("SELECT AVG(rating), COUNT(*) FROM reviews WHERE provider_id=?", (provider_id,)).fetchone()
    avg_rating_value = round(avg_rating[0], 1) if avg_rating[0] else 0
    
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
        # Check if user already reviewed
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
    return render_page(p['name'], content, 'list')

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

        # ------------------------------------------------------------
# BOOST SYSTEM (Profile, Job, Vendor)
# ------------------------------------------------------------
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
    return render_page('Boost Profile', content)

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
    return render_page('Boost Submitted', content)

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
    return render_page('Boost Job', content)

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
    return render_page('Boost Submitted', content)

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
    return render_page('Boost Vendor', content)

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
    return render_page('Boost Submitted', content)

# ------------------------------------------------------------
# ADMIN PANEL
# ------------------------------------------------------------
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
            return render_page('Admin Login', content)
    
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
        return render_page('Admin Login', content)
    
    db = get_db()
    
    # Handle approve/reject actions
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
    open_jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE status='Open'").fetchone()[0]
    pending_boosts = db.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'").fetchone()[0]
    
    # Get pending requests
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
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-chart-line"></i> Dashboard Statistics</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
            <div class="stat-card"><h3>{total_users}</h3><small>Total Users</small></div>
            <div class="stat-card"><h3>{total_providers}</h3><small>Freelancers</small></div>
            <div class="stat-card"><h3>{total_vendors}</h3><small>Vendors</small></div>
            <div class="stat-card"><h3>{open_jobs}</h3><small>Open Jobs</small></div>
            <div class="stat-card"><h3>{pending_boosts}</h3><small>Pending Boosts</small></div>
        </div>
    </div>
    
    <div class="card">
        <div class="card-header"><i class="fas fa-clock"></i> Pending Boost Requests</div>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>ID</th><th>User</th><th>Transaction</th><th>Plan</th><th>Type</th><th>Date</th><th>Action</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        <div style="margin-top: 20px; display: flex; gap: 10px;">
            <a href="/admin/stats" class="btn btn-outline"><i class="fas fa-chart-bar"></i> Detailed Statistics</a>
            <a href="/admin/logout" class="btn btn-small btn-danger"><i class="fas fa-sign-out-alt"></i> Logout</a>
        </div>
    </div>
    """
    return render_page('Admin Dashboard', content)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin')

@app.route('/admin/stats')
def admin_stats():
    if not session.get('admin'):
        return redirect('/admin')
    
    db = get_db()
    
    # Basic stats
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_providers = db.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
    total_vendors = db.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
    
    # Job stats
    job_counts = db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
    job_stats = {row['status']: row[1] for row in job_counts}
    
    # Vendor stats
    vendor_counts = db.execute("SELECT status, COUNT(*) FROM vendors GROUP BY status").fetchall()
    vendor_stats = {row['status']: row[1] for row in vendor_counts}
    
    # Boost stats
    pending_boosts = db.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'").fetchone()[0]
    approved_boosts = db.execute("SELECT COUNT(*) FROM boost_requests WHERE status='approved'").fetchone()[0]
    
    # Revenue calculation
    revenue = 0
    approved_plans = db.execute("SELECT plan FROM boost_requests WHERE status='approved'").fetchall()
    for row in approved_plans:
        plan = int(row['plan'])
        if plan == 7:
            revenue += 5000
        elif plan == 30:
            revenue += 15000
    
    # Top skills
    skills_data = db.execute("SELECT skills FROM providers WHERE skills IS NOT NULL AND skills != ''").fetchall()
    skill_counter = defaultdict(int)
    for row in skills_data:
        for skill in row['skills'].split(','):
            skill = skill.strip().title()
            if skill:
                skill_counter[skill] += 1
    top_skills = sorted(skill_counter.items(), key=lambda x: x[1], reverse=True)[:5]
    top_skills_html = "".join(f"<tr><td>{skill}</td><td>{cnt}</td></tr>" for skill, cnt in top_skills)
    
    content = f"""
    <div class="card">
        <div class="card-header"><i class="fas fa-chart-bar"></i> Detailed Statistics</div>
        
        <h3>📊 Platform Overview</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-bottom: 30px;">
            <div class="stat-card"><h3>{total_users}</h3><small>Total Users</small></div>
            <div class="stat-card"><h3>{total_providers}</h3><small>Freelancers</small></div>
            <div class="stat-card"><h3>{total_vendors}</h3><small>Vendors</small></div>
            <div class="stat-card"><h3>{job_stats.get('Open', 0)}</h3><small>Open Jobs</small></div>
            <div class="stat-card"><h3>{job_stats.get('Taken', 0)}</h3><small>Taken Jobs</small></div>
            <div class="stat-card"><h3>{job_stats.get('Closed', 0)}</h3><small>Closed Jobs</small></div>
            <div class="stat-card"><h3>{vendor_stats.get('Open', 0)}</h3><small>Open Vendors</small></div>
            <div class="stat-card"><h3>{vendor_stats.get('Closed', 0)}</h3><small>Closed Vendors</small></div>
            <div class="stat-card"><h3>{pending_boosts}</h3><small>Pending Boosts</small></div>
            <div class="stat-card"><h3>{approved_boosts}</h3><small>Approved Boosts</small></div>
            <div class="stat-card"><h3>UGX {revenue:,}</h3><small>Est. Revenue</small></div>
        </div>
        
        <h3>💪 Top 5 Skills</h3>
        <table style="width: 100%; margin-bottom: 30px;">
            <thead><tr><th>Skill</th><th>Freelancers</th></tr></thead>
            <tbody>{top_skills_html or '<tr><td colspan="2">No skills yet</td></tr>'}</tbody>
        </table>
        
        <div style="margin-top: 20px;">
            <a href="/admin" class="btn btn-outline"><i class="fas fa-arrow-left"></i> Back to Admin Panel</a>
            <a href="/admin/logout" class="btn btn-small btn-danger"><i class="fas fa-sign-out-alt"></i> Logout</a>
        </div>
    </div>
    """
    return render_page('Admin Statistics', content)

# ------------------------------------------------------------
# PWA ROUTES (Progressive Web App)
# ------------------------------------------------------------
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
            {
                "src": "/static/icon-192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/icon-512.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }
    import json
    resp = make_response(json.dumps(manifest_content))
    resp.headers['Content-Type'] = 'application/json'
    return resp

@app.route('/service-worker.js')
def service_worker():
    sw_content = '''
const CACHE_NAME = 'rockabyconnect-v1';
const urlsToCache = [
    '/',
    '/static/icon-192.png',
    '/static/icon-512.png'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(urlsToCache))
    );
});

self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => response || fetch(event.request))
    );
});
'''
    resp = make_response(sw_content)
    resp.headers['Content-Type'] = 'application/javascript'
    return resp

# ------------------------------------------------------------
# INITIALIZE DATABASE & RUN APP
# ------------------------------------------------------------
# Initialize database on startup
with app.app_context():
    init_db()

@app.route('/edit-name')
@login_required
def edit_name():
    content = f"""
    <div class="card" style="max-width: 500px; margin: 0 auto;">
        <div class="card-header"><i class="fas fa-user-edit"></i> Edit Your Name</div>
        <form method="POST" action="/update-name">
            <label><i class="fas fa-user"></i> Full Name *</label>
            <input type="text" name="name" value="{session['user_name']}" required>
            <button type="submit" class="btn" style="width: 100%; margin-top: 20px;"><i class="fas fa-save"></i> Update Name</button>
        </form>
    </div>
    """
    return render_page('Edit Name', content)

@app.route('/update-name', methods=['POST'])
@login_required
def update_name():
    new_name = request.form['name'].strip()
    if not new_name:
        return "Name cannot be empty. <a href='/edit-name'>Back</a>"
    db = get_db()
    db.execute("UPDATE users SET name=? WHERE id=?", (new_name, session['user_id']))
    db.commit()
    session['user_name'] = new_name
    return redirect('/dashboard')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
