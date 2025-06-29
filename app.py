from flask import Flask, render_template_string, request, redirect, url_for, session, abort, jsonify
import sqlite3
from config import Config
from datetime import datetime, timedelta
import os
import secrets
import json
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
from contextlib import contextmanager
import random
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
import time
import re
from urllib.parse import urlparse
import uuid


# Load environment variables
load_dotenv()

@contextmanager
def get_db():
    conn = sqlite3.connect('ecommerce.db')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
csrf = CSRFProtect(app)

# Rate limiting for admin login
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://",  # For production, use Redis: 'redis://localhost:6379/0'
    default_limits=["200 per day", "50 per hour"]
)

def init_db():
    try:
        conn = sqlite3.connect('ecommerce.db')
        c = conn.cursor()
        
        
        c.execute('''CREATE TABLE IF NOT EXISTS products
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    price REAL NOT NULL,
                    image TEXT,
                    min_quantity INTEGER DEFAULT 1,
                    max_quantity INTEGER DEFAULT 10,
                    discount INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0,
                    stock INTEGER DEFAULT 100,
                    images TEXT,  
                    youtube_url TEXT,
                    category TEXT,
                    tags TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS users
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    name TEXT,
                    email TEXT,
                    address TEXT,
                    state TEXT,
                    city TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS orders
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_date TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            state TEXT NOT NULL,
            city TEXT NOT NULL,
            address TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            subtotal REAL NOT NULL,
            delivery_charge REAL NOT NULL,
            total_amount REAL NOT NULL,
            advance_payment REAL NOT NULL,
            items TEXT NOT NULL,
            user_id INTEGER,
            status TEXT DEFAULT 'Processing',
            can_cancel INTEGER DEFAULT 1,
            FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        
        c.execute("PRAGMA table_info(orders)")
        columns = [col[1] for col in c.fetchall()]
        if 'can_cancel' not in columns:
            c.execute("ALTER TABLE orders ADD COLUMN can_cancel INTEGER DEFAULT 1")
        
        c.execute("SELECT COUNT(*) FROM products")
        if c.fetchone()[0] == 0:
            sample_products = [
                ("Smartphone", "Latest model with great camera", 15000.0, "phone1.jpg", 1, 5, 10, 4.5, 50, 
                '["phone1_1.jpg", "phone1_2.jpg", "phone1_3.jpg"]', 'https://youtu.be/sample1', 'Electronics', '["mobile", "smartphone"]'),
                ("Laptop", "High performance laptop", 45000.0, "laptop.jpg", 1, 3, 15, 4.8, 30,
                '["laptop_1.jpg", "laptop_2.jpg", "laptop_3.jpg"]', 'https://youtu.be/sample2', 'Electronics', '["laptop", "computer"]'),
                ("Smart Watch", "Fitness tracker with heart rate monitor", 5000.0, "watch.jpg", 1, 2, 5, 4.2, 40,
                '["watch_1.jpg", "watch_2.jpg"]', 'https://youtu.be/sample3', 'Electronics', '["wearable", "fitness"]'),
                ("Wireless Earbuds", "Noise cancelling wireless earbuds", 3000.0, "earbuds.jpg", 1, 4, 8, 4.3, 60,
                '["earbuds_1.jpg", "earbuds_2.jpg", "earbuds_3.jpg"]', 'https://youtu.be/sample4', 'Electronics', '["audio", "earphones"]')
            ]
            c.executemany("INSERT INTO products (title, description, price, image, min_quantity, max_quantity, discount, rating, stock, images, youtube_url, category, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                         sample_products)
        
        conn.commit()
    except Exception as e:
        print(f"Database error: {e}")
        conn.rollback()
    finally:
        conn.close()

init_db()

DELIVERY_CHARGES = {
    "Madhya Pradesh": {
        "Ambah": 500,
        "Gwalior": 300,
        "Bhopal": 200,
        "Indore": 200
    },
    "Uttar Pradesh": {
        "Agra": 400,
        "Lucknow": 300,
        "Varanasi": 350,
        "Kanpur": 300
    },
    "Rajasthan": {
        "Jaipur": 300,
        "Udaipur": 350,
        "Jodhpur": 400,
        "Kota": 350
    }
}





# Add these configurations at the top of your admin routes
app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
    

def get_related_products(product_id, category=None, limit=4):
    try:
        with get_db() as conn:
            c = conn.cursor()
            if category:
                c.execute("SELECT * FROM products WHERE category = ? AND id != ? ORDER BY RANDOM() LIMIT ?", 
                         (category, product_id, limit))
            else:
                c.execute("SELECT * FROM products WHERE id != ? ORDER BY RANDOM() LIMIT ?", 
                         (product_id, limit))
            return c.fetchall()
    except Exception as e:
        print(f"Error fetching related products: {e}")
        return []

def get_random_products(limit=8):
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM products ORDER BY RANDOM() LIMIT ?", (limit,))
            return c.fetchall()
    except Exception as e:
        print(f"Error fetching random products: {e}")
        return []

def get_user_profile(user_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return c.fetchone()
    except Exception as e:
        print(f"Error fetching user profile: {e}")
        return None

def can_cancel_order(order_date):
    order_datetime = datetime.strptime(order_date, "%Y-%m-%d %H:%M:%S")
    return datetime.now() - order_datetime < timedelta(days=1)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone']
        
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM users WHERE phone = ?", (phone,))
                user = c.fetchone()
                
                if not user:
                    c.execute("INSERT INTO users (phone) VALUES (?)", (phone,))
                    conn.commit()
                    user_id = c.lastrowid
                else:
                    user_id = user[0]
                
                session['user_id'] = user_id
                session['user_phone'] = phone
                
                return redirect(url_for('index'))
        
        except Exception as e:
            print(f"Login error: {e}")
            return "An error occurred during login", 500
    
    return render_template_string('''
        <!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --primary-color: #4361ee;
            --secondary-color: #3a0ca3;
            --accent-color: #f72585;
            --light-color: #f8f9fa;
            --dark-color: #212529;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            max-width: 400px; 
            margin: 0 auto; 
            padding: 20px; 
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%);
            min-height: 100vh;
        }
        
        form { 
            display: flex; 
            flex-direction: column; 
            gap: 15px;
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            border: 1px solid rgba(255,255,255,0.3);
            transform: perspective(500px) translateZ(0);
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        form:hover {
            transform: perspective(500px) translateZ(10px);
            box-shadow: 0 15px 35px rgba(0,0,0,0.15);
        }
        
        input, button { 
            padding: 12px 15px;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        input:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        button { 
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%); 
            color: white; 
            border: none; 
            cursor: pointer; 
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            position: relative;
            overflow: hidden;
        }
        
        button:hover {
            background: linear-gradient(135deg, var(--secondary-color) 0%, var(--primary-color) 100%);
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
            transform: translateY(-2px);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        button::after {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: rgba(255,255,255,0.1);
            transform: rotate(45deg);
            transition: all 0.3s;
        }
        
        button:hover::after {
            left: 100%;
        }
        
        .desktop-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 0;
            margin-bottom: 30px;
            border-bottom: 1px solid rgba(0,0,0,0.1);
        }
        
        .desktop-nav a {
            text-decoration: none;
            color: var(--dark-color);
            font-weight: 500;
            margin-left: 20px;
            padding: 8px 12px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .desktop-nav a:first-child {
            font-size: 24px;
            font-weight: bold;
            color: var(--primary-color);
            margin-left: 0;
        }
        
        .desktop-nav a:hover {
            color: var(--primary-color);
            background: rgba(67, 97, 238, 0.1);
        }
        
        h2 {
            text-align: center;
            color: var(--dark-color);
            margin-bottom: 25px;
            font-size: 28px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--accent-color) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .desktop-nav { display: none; }
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: white; 
                box-shadow: 0 -5px 15px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 12px 0;
                z-index: 1000;
                border-top-left-radius: 15px;
                border-top-right-radius: 15px;
                backdrop-filter: blur(10px);
                background: rgba(255,255,255,0.9);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                position: relative;
                padding: 5px 10px;
                border-radius: 10px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary-color);
                background: rgba(67, 97, 238, 0.1);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: translateY(-3px);
            }
            
            .cart-count {
                position: absolute;
                top: -5px;
                right: -5px;
                background: var(--accent-color);
                color: white;
                border-radius: 50%;
                width: 18px;
                height: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 10px;
                font-weight: bold;
            }
            
            body { padding-bottom: 80px; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="desktop-nav">
        <a href="/">CRONYZO</a>
        <div>
            <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
            {% if 'user_id' in session %}
                <a href="{{ url_for('my_orders') }}">Orders</a>
                <a href="{{ url_for('account') }}">Account</a>
                <a href="{{ url_for('logout') }}">Logout</a>
            {% else %}
                <a href="{{ url_for('login') }}">Login</a>
            {% endif %}
        </div>
    </div>
    
    <h2>Login with WhatsApp</h2>
    <form method="post">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="tel" name="phone" placeholder="WhatsApp Number" required>
        <button type="submit">Continue</button>
    </form>
    
    <div class="mobile-nav">
        <a href="{{ url_for('index') }}">
            <i class="fas fa-home"></i>
            <span>Home</span>
        </a>
        <a href="{{ url_for('cart') }}">
            <i class="fas fa-shopping-cart"></i>
            <span>Cart</span>
            {% if session.get('cart') %}
            <span class="cart-count">{{ session['cart']|length }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('my_orders') }}">
            <i class="fas fa-box"></i>
            <span>Orders</span>
        </a>
        <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
            <i class="fas fa-user"></i>
            <span>Account</span>
        </a>
    </div>
</body>
</html>
    ''')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_phone', None)
    return redirect(url_for('index'))

@app.route('/')
def index():
    search_query = request.args.get('search', '')
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            if search_query:
                c.execute("SELECT * FROM products WHERE title LIKE ? OR description LIKE ? OR tags LIKE ?", 
                         (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
            else:
                c.execute("SELECT * FROM products ORDER BY RANDOM() LIMIT 12")
            
            products = []
            for product in c.fetchall():
                products.append({
                    'id': product[0],
                    'title': product[1],
                    'description': product[2],
                    'price': product[3],
                    'image': product[4],
                    'min_quantity': product[5],
                    'max_quantity': product[6],
                    'discount': product[7] if len(product) > 7 else 0,
                    'rating': product[8] if len(product) > 8 else 0,
                    'stock': product[9] if len(product) > 9 else 0
                })
                
    except Exception as e:
        print(f"Error fetching products: {e}")
        products = []
    
    if 'cart' not in session:
        session['cart'] = {}
    
    return render_template_string('''
        <!DOCTYPE html>
<html>
<head>
    <title>CRONYZO</title>
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0; 
            padding: 0; 
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
        }
        
        .header { 
            background: rgba(255,255,255,0.95); 
            padding: 15px; 
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky; 
            top: 0; 
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .products { 
            display: grid; 
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
            gap: 25px; 
            padding: 25px; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .product-card { 
            padding: 0 10px;
            background: white; 
            border-radius: 12px; 
            overflow: hidden; 
            box-shadow: 0 10px 20px rgba(0,0,0,0.08);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            position: relative;
            transform: perspective(500px) translateZ(0);
        }
        
        .product-card:hover { 
            transform: perspective(500px) translateZ(15px);
            box-shadow: 0 15px 30px rgba(0,0,0,0.15);
        }
        
        .product-image { 
            width: 100%; 
            height: 200px; 
            object-fit: cover; 
            cursor: pointer; 
            transition: transform 0.5s;
        }
        
        .product-card:hover .product-image {
            transform: scale(1.03);
        }
        
        .cart-count { 
            background: var(--accent); 
            color: white; 
            border-radius: 50%; 
            padding: 2px 6px; 
            font-size: 12px; 
            font-weight: bold;
        }
        
        .mobile-nav { display: none; }
        
        .search-container { 
            max-width: 1200px; 
            margin: 25px auto; 
            padding: 0 25px; 
        }
        
        .search-container form {
            display: flex;
            gap: 15px;
        }
        
        .search-container input {
            flex: 1;
            padding: 12px 20px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            transition: all 0.3s;
        }
        
        .search-container input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .search-container button {
            padding: 12px 25px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            transition: all 0.3s;
        }
        
        .search-container button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .discount-badge { 
            position: absolute; 
            top: 10px; 
            right: 10px; 
            background: linear-gradient(135deg, #ff4757 0%, #ff6b81 100%); 
            color: white; 
            padding: 5px 10px; 
            border-radius: 20px; 
            font-size: 12px; 
            font-weight: bold;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            z-index: 1;
        }
        
        .product-card-container { 
            position: relative; 
        }
        
        .product-info { 
            padding: 20px; 
        }
        
        .product-info h3 {
            margin: 0 0 10px 0;
            font-size: 16px;
            color: var(--dark);
        }
        
        .product-info a {
            display: inline-block;
            margin-top: 15px;
            padding: 10px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            width: 100%;
            text-align: center;
            font-weight: 500;
            transition: all 0.3s;
        }
        
        .product-info a:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(67, 97, 238, 0.4);
        }
        
        @media (max-width: 768px) {
            .desktop-nav { display: none; }
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            .products { 
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); 
                gap: 15px; 
                padding: 15px; 
            }
            
            .product-image { height: 150px; }
            
            body { padding-bottom: 80px; }
        }
        
        /* Admin Access Lock Icon */
        .admin-lock-icon {
            position: fixed;
            bottom: 70px;
            right: 20px;
            width: 50px;
            height: 50px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            z-index: 9999;
            box-shadow: 0 5px 20px rgba(67, 97, 238, 0.4);
            transition: all 0.3s;
        }
        
        .admin-lock-icon:hover {
            transform: scale(1.1) rotate(10deg);
            box-shadow: 0 8px 25px rgba(67, 97, 238, 0.5);
        }
        
        .click-counter {
            position: fixed;
            bottom: 75px;
            right: 20px;
            background: var(--accent);
            color: white;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            display: none;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
            z-index: 10000;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="header">
        <div class="navbar desktop-nav">
            <a href="/">CRONYZO</a>
            <div>
                <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session['cart']|length }}</span>)</a>
                {% if 'user_id' in session %}
                    <a href="{{ url_for('my_orders') }}">Orders</a>
                    <a href="{{ url_for('account') }}">Account</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}">Login</a>
                {% endif %}
            </div>
        </div>
    </div>
    
    <div class="search-container">
        <form method="get" action="/">
            <input type="text" name="search" placeholder="Search products..." value="{{ search_query }}">
            <button type="submit">Search</button>
        </form>
    </div>
    
    <div class="products">
        {% for product in products %}
        <div class="product-card">
            <div class="product-card-container">
                {% if product.discount > 0 %}
                <span class="discount-badge">{{ product.discount }}% OFF</span>
                {% endif %}
                <img src="{{ url_for('static', filename='images/' + product.image) if product.image else 'https://via.placeholder.com/300' }}" 
                     class="product-image" 
                     alt="{{ product.title }}"
                     onclick="window.location.href='{{ url_for('product_detail', product_id=product.id) }}'">
            </div>
            <div class="product-info">
                <h3>{{ product.title }}</h3>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <p style="font-weight: bold; color: var(--primary);">₹{{ "{:,.2f}".format(product.price * (1 - product.discount/100)) }}</p>
                    {% if product.discount > 0 %}
                    <p style="text-decoration: line-through; color: #777; font-size: 0.9em;">₹{{ "{:,.2f}".format(product.price) }}</p>
                    {% endif %}
                </div>
                <div style="display: flex; align-items: center; margin-top: 5px;">
                    <span style="color: var(--warning);">★</span>
                    <span style="margin-left: 5px; font-size: 0.9em;">{{ product.rating }}</span>
                </div>
                <a href="{{ url_for('product_detail', product_id=product.id) }}">
                    View Details
                </a>
            </div>
        </div>
        {% endfor %}
    </div>
    
    <div class="mobile-nav">
        <a href="{{ url_for('index') }}">
            <i class="fas fa-home"></i>
            <span>Home</span>
        </a>
        
        <a href="{{ url_for('cart') }}">
            <i class="fas fa-shopping-cart"></i>
            <span>Cart</span>
            {% if session.get('cart') %}
            <span class="cart-count">{{ session['cart']|length }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('my_orders') }}">
            <i class="fas fa-box"></i>
            <span>Orders</span>
        </a>
        <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
            <i class="fas fa-user"></i>
            <span>Account</span>
        </a>
    </div>

    <!-- Admin Access Button -->
    <div class="admin-lock-icon" id="adminLock">
        <i class="fas fa-lock"></i>
    </div>
    <div class="click-counter" id="clickCounter"></div>

    <script>
        // Admin access functionality
        let adminClickCount = 0;
        const adminLock = document.getElementById('adminLock');
        const clickCounter = document.getElementById('clickCounter');
        let resetTimer;

        adminLock.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            adminClickCount++;
            clickCounter.textContent = adminClickCount;
            clickCounter.style.display = 'flex';
            
            // Reset counter after 3 seconds of inactivity
            clearTimeout(resetTimer);
            resetTimer = setTimeout(() => {
                adminClickCount = 0;
                clickCounter.style.display = 'none';
            }, 3000);
            
            if (adminClickCount >= 5) {
                adminClickCount = 0;
                clickCounter.style.display = 'none';
                window.location.href = "/hidden-admin";
            }
        });

        // Original hidden area still works as backup
        document.addEventListener('click', function(e) {
            if (e.clientX > window.innerWidth - 50 && e.clientY > window.innerHeight - 50) {
                adminClickCount++;
                if (adminClickCount >= 5) {
                    adminClickCount = 0;
                    window.location.href = "/hidden-admin";
                }
            }
        });
        
        // For jQuery AJAX
        $.ajaxSetup({
            beforeSend: function(xhr, settings) {
                if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type)) {
                    xhr.setRequestHeader("X-CSRFToken", "{{ csrf_token() }}");
                }
            }
        });

        // Or for individual fetch requests
        fetch('/some-endpoint', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify(data)
        });
    </script>
</body>
</html>
    ''', products=products, search_query=search_query)


    
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = c.fetchone()
            
            if not product:
                return "Product not found", 404
                
            # Convert sqlite3.Row to dictionary and handle missing fields
            product_dict = dict(product)
            
            # Safely parse JSON fields
            images = []
            if 'images' in product_dict and product_dict['images']:
                try:
                    images = json.loads(product_dict['images'])
                except json.JSONDecodeError:
                    images = []
            
            tags = []
            if 'tags' in product_dict and product_dict['tags']:
                try:
                    tags = json.loads(product_dict['tags'])
                except json.JSONDecodeError:
                    tags = []
            
            product_data = {
                'id': product_dict.get('id', 0),
                'title': product_dict.get('title', ''),
                'description': product_dict.get('description', ''),
                'price': product_dict.get('price', 0),
                'image': product_dict.get('image', ''),
                'min_quantity': product_dict.get('min_quantity', 1),
                'max_quantity': product_dict.get('max_quantity', 10),
                'discount': product_dict.get('discount', 0),
                'rating': product_dict.get('rating', 0),
                'stock': product_dict.get('stock', 0),
                'images': images,
                'youtube_url': product_dict.get('youtube_url', ''),
                'category': product_dict.get('category', ''),
                'tags': tags
            }
            
            related_products = get_related_products(product_id, product_data.get('category'))
    except Exception as e:
        print(f"Error fetching product: {e}")
        return "Product not found", 404
    
    return render_template_string('''
        <!DOCTYPE html>
<html>
<head>
    <title>{{ product.title }} - CRONYZO</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
            --danger: #ff4757;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 10px;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
        }
        
        .header { 
            background: rgba(255,255,255,0.95);
            padding: 15px 0;
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
            margin-bottom: 20px;
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto;
            padding: 0 20px;
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .product-container { 
            display: grid; 
            padding: 8px 10px;                      
            grid-template-columns: 1fr 1fr; 
            gap: 40px;
            background: white;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 15px 30px rgba(0,0,0,0.08);
            transform: perspective(500px) translateZ(0);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        
        .product-container:hover {
            transform: perspective(500px) translateZ(10px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.12);
        }
        
        .product-image { 
            width: 100%; 
            max-height: 500px; 
            object-fit: contain; 
            cursor: zoom-in;
            transition: transform 0.5s;
            padding: 20px;
        }
        
        .product-image:hover {
            transform: scale(1.02);
        }
        
        .product-title { 
            font-size: 28px; 
            margin-bottom: 10px;
            color: var(--dark);
            font-weight: 700;
        }
        
        .product-price { 
            font-size: 24px; 
            color: var(--primary); 
            font-weight: bold; 
            margin: 20px 0;
            display: flex;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        
        .original-price { 
            text-decoration: line-through; 
            color: #777; 
            font-size: 18px; 
        }
        
        .discount-percent { 
            color: var(--danger); 
            font-weight: bold;
            background: rgba(255, 71, 87, 0.1);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 16px;
        }
        
        .btn { 
            display: inline-block; 
            padding: 12px 30px; 
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white; 
            text-decoration: none; 
            border-radius: 8px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(67, 97, 238, 0.4);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .thumbnail-container { 
            display: flex; 
            gap: 15px; 
            margin-top: 20px; 
            flex-wrap: wrap;
            padding: 0 20px 20px;
        }
        
        .thumbnail { 
            width: 80px; 
            height: 80px; 
            object-fit: cover; 
            cursor: pointer; 
            border: 2px solid transparent;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .thumbnail:hover {
            transform: scale(1.05);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .thumbnail.active { 
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .video-container { 
            margin-top: 30px;
            padding: 0 20px 20px;
        }
        
        .video-container h3 {
            margin-bottom: 15px;
            color: var(--dark);
            font-size: 20px;
        }
        
        .related-products { 
            margin-top: 60px; 
        }
        
        .related-title { 
            font-size: 24px; 
            margin-bottom: 25px; 
            padding-bottom: 15px; 
            border-bottom: 1px solid rgba(0,0,0,0.1);
            color: var(--dark);
            font-weight: 600;
        }
        
        .mobile-nav { display: none; }
        
        .zoom-modal { 
            display: none; 
            position: fixed; 
            top: 0; 
            left: 0; 
            right: 0; 
            bottom: 0; 
            background: rgba(0,0,0,0.95); 
            z-index: 2000;
            backdrop-filter: blur(5px);
        }
        
        .zoom-image { 
            max-width: 90%; 
            max-height: 90%; 
            position: absolute; 
            top: 50%; 
            left: 50%; 
            transform: translate(-50%, -50%);
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
            border-radius: 8px;
        }
        
        .close-zoom { 
            position: absolute; 
            top: 30px; 
            right: 30px; 
            color: white; 
            font-size: 40px; 
            cursor: pointer;
            text-shadow: 0 2px 5px rgba(0,0,0,0.5);
            transition: all 0.3s;
        }
        
        .close-zoom:hover {
            transform: rotate(90deg);
            color: var(--accent);
        }
        
        a[style*="Back to products"] {
            display: inline-block;
            margin-bottom: 25px;
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s;
            padding: 8px 15px;
            border-radius: 8px;
        }
        
        a[style*="Back to products"]:hover {
            background: rgba(67, 97, 238, 0.1);
            transform: translateX(-5px);
        }
        
        form[method="post"] {
            margin: 30px 0;
        }
        
        form[method="post"] input[type="number"] {
            padding: 10px 15px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            margin-left: 10px;
            transition: all 0.3s;
        }
        
        form[method="post"] input[type="number"]:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .tag {
            display: inline-block; 
            background: linear-gradient(135deg, #f1f1f1 0%, #e0e0e0 100%); 
            padding: 5px 12px; 
            border-radius: 20px; 
            margin: 5px; 
            font-size: 0.9em;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            transition: all 0.3s;
        }
        
        .tag:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 10px rgba(0,0,0,0.1);
        }
        
        @media (max-width: 768px) {
            .product-container { 
                grid-template-columns: 1fr;
                border-radius: 0;
                box-shadow: none;
            }
            
            .desktop-nav { display: none; }
            
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
            
            .product-title {
                font-size: 24px;
            }
            
            .product-price {
                font-size: 20px;
            }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="header">
        <div class="navbar desktop-nav">
            <a href="/">CRONYZO</a>
            <div>
                <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                {% if 'user_id' in session %}
                    <a href="{{ url_for('my_orders') }}">Orders</a>
                    <a href="{{ url_for('account') }}">Account</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}">Login</a>
                {% endif %}
            </div>
        </div>
    </div>
    
    <a href="{{ url_for('index') }}" style="display: inline-block; margin-bottom: 20px;">&larr; Back to products</a>
    
    <div class="product-container">
        <div>
            <img src="{{ url_for('static', filename='images/' + product.image) if product.image else 'https://via.placeholder.com/500' }}" 
                 class="product-image" 
                 alt="{{ product.title }}"
                 onclick="zoomImage(this.src)">
            
            {% if product.images %}
            <div class="thumbnail-container">
                <img src="{{ url_for('static', filename='images/' + product.image) if product.image else 'https://via.placeholder.com/500' }}" 
                     class="thumbnail active" 
                     onclick="changeMainImage(this.src, this)"
                     alt="{{ product.title }}">
                {% for img in product.images %}
                <img src="{{ url_for('static', filename='images/' + img) }}" 
                     class="thumbnail" 
                     onclick="changeMainImage(this.src, this)"
                     alt="{{ product.title }}">
                {% endfor %}
            </div>
            {% endif %}
            
            {% if product.youtube_url %}
            <div class="video-container">
                <h3>Product Video</h3>
                <iframe width="100%" height="315" src="{{ product.youtube_url.replace('youtu.be', 'youtube.com/embed') }}" 
                        frameborder="0" allowfullscreen></iframe>
            </div>
            {% endif %}
        </div>
        
        <div style="padding: 30px 20px 30px 0;">
            <h1 class="product-title">{{ product.title }}</h1>
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                <span style="color: var(--warning);">★</span>
                <span>{{ product.rating }}</span>
                <span style="color: #777;">|</span>
                <span style="color: {{ 'var(--success)' if product.stock > 0 else 'var(--danger)' }};">
                    {{ product.stock }} in stock
                </span>
            </div>
            
            <div class="product-price">
                ₹{{ "{:,.2f}".format(product.price * (1 - product.discount/100)) }}
                {% if product.discount > 0 %}
                <span class="original-price">₹{{ "{:,.2f}".format(product.price) }}</span>
                <span class="discount-percent">{{ product.discount }}% OFF</span>
                {% endif %}
            </div>
            
            <p style="line-height: 1.6; color: #555;">{{ product.description }}</p>
            
            <form method="post" action="{{ url_for('add_to_cart', product_id=product.id) }}" style="margin: 20px 0;">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <div style="margin-bottom: 15px;">
                    <label style="font-weight: 500;">Quantity: </label>
                    <input type="number" name="quantity" value="{{ product.min_quantity }}" 
                           min="{{ product.min_quantity }}" max="{{ product.max_quantity }}" style="padding: 8px;">
                </div>
                <button type="submit" class="btn">Add to Cart</button>
            </form>
            
            <div style="margin-top: 30px;">
                <p><strong>Availability:</strong> <span style="color: {{ 'var(--success)' if product.stock > 0 else 'var(--danger)' }};">
                    {{ 'In Stock' if product.stock > 0 else 'Out of Stock' }}
                </span></p>
                <p><strong>Min Order:</strong> {{ product.min_quantity }} units</p>
                <p><strong>Max Order:</strong> {{ product.max_quantity }} units</p>
                {% if product.tags %}
                <div style="margin-top: 15px;">
                    <strong>Tags:</strong>
                    {% for tag in product.tags %}
                    <span class="tag">{{ tag }}</span>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
        </div>
    </div>
    
    {% if related_products %}
    <div class="related-products">
        <h3 class="related-title">You may also like</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 25px;">
            {% for related in related_products %}
            <div style="background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 20px rgba(0,0,0,0.08); transition: all 0.3s;">
                <img src="{{ url_for('static', filename='images/' + related[4]) if related[4] else 'https://via.placeholder.com/300' }}" 
                     style="width: 100%; height: 200px; object-fit: cover; cursor: pointer; transition: transform 0.5s;" 
                     onclick="window.location.href='{{ url_for('product_detail', product_id=related[0]) }}'"
                     alt="{{ related[1] }}">
                <div style="padding: 20px;">
                    <h4 style="margin: 0 0 10px 0; font-size: 16px; color: var(--dark);">{{ related[1] }}</h4>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: bold; color: var(--primary);">₹{{ "{:,.2f}".format(related[3] * (1 - related[7]/100)) }}</span>
                        <a href="{{ url_for('product_detail', product_id=related[0]) }}" 
                           style="padding: 6px 12px; background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%); color: white; text-decoration: none; border-radius: 6px; font-size: 0.8em; transition: all 0.3s;">
                            View
                        </a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}
    
    <div class="zoom-modal" id="zoomModal" onclick="closeZoom()">
        <span class="close-zoom" onclick="event.stopPropagation(); closeZoom()">&times;</span>
        <img class="zoom-image" id="zoomedImage">
    </div>
    
    <div class="mobile-nav">
        <a href="{{ url_for('index') }}">
            <i class="fas fa-home"></i>
            <span>Home</span>
        </a>
        
        <a href="{{ url_for('cart') }}">
            <i class="fas fa-shopping-cart"></i>
            <span>Cart</span>
            {% if session.get('cart') %}
            <span class="cart-count">{{ session['cart']|length }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('my_orders') }}">
            <i class="fas fa-box"></i>
            <span>Orders</span>
        </a>
        <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
            <i class="fas fa-user"></i>
            <span>Account</span>
        </a>
    </div>
    
    <script>
        function changeMainImage(src, element) {
            document.querySelector('.product-image').src = src;
            document.querySelectorAll('.thumbnail').forEach(thumb => {
                thumb.classList.remove('active');
            });
            element.classList.add('active');
        }
        
        function zoomImage(src) {
            const modal = document.getElementById('zoomModal');
            const zoomedImg = document.getElementById('zoomedImage');
            zoomedImg.src = src;
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
        }
        
        function closeZoom() {
            document.getElementById('zoomModal').style.display = 'none';
            document.body.style.overflow = 'auto';
        }
        
        // Close modal when clicking outside the image
        document.getElementById('zoomModal').addEventListener('click', function(e) {
            if (e.target === this) {
                closeZoom();
            }
        });
    </script>
</body>
</html>
    ''', product=product_data, related_products=related_products)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        quantity = int(request.form['quantity'])
        
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = c.fetchone()
            
            if not product:
                return "Product not found", 404
            
            if 'cart' not in session:
                session['cart'] = {}
            
            cart = session['cart']
            if str(product_id) in cart:
                cart[str(product_id)]['quantity'] += quantity
            else:
                cart[str(product_id)] = {
                    'id': product_id,
                    'title': product[1],
                    'price': product[3],
                    'quantity': quantity,
                    'image': product[4],
                    'max_quantity': product[6],
                    'discount': product[7]
                }
            
            session['cart'] = cart
            return redirect(url_for('cart'))
    
    except Exception as e:
        print(f"Error adding to cart: {e}")
        return "An error occurred", 500

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'cart' not in session or not session['cart']:
        return render_template_string('''
            <!DOCTYPE html>
<html>
<head>
    <title>Your Cart</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            max-width: 800px; 
            margin: 0 auto; 
            padding: 20px;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
        }
        
        .header { 
            background: rgba(255,255,255,0.95);
            padding: 15px 0;
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
            margin-bottom: 30px;
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 800px; 
            margin: 0 auto;
            padding: 0 20px;
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .empty-cart { 
            text-align: center; 
            padding: 80px 0;
            background: white;
            border-radius: 16px;
            box-shadow: 0 15px 30px rgba(0,0,0,0.08);
            transform: perspective(500px) translateZ(0);
            transition: all 0.3s;
            margin: 20px 0;
        }
        
        .empty-cart:hover {
            transform: perspective(500px) translateZ(10px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.12);
        }
        
        .empty-cart h2 {
            font-size: 28px;
            color: var(--dark);
            margin-bottom: 20px;
            font-weight: 600;
        }
        
        .btn { 
            display: inline-block; 
            padding: 12px 30px; 
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white; 
            text-decoration: none; 
            border-radius: 8px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(67, 97, 238, 0.4);
            background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 100%);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .btn::after {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: rgba(255,255,255,0.1);
            transform: rotate(45deg);
            transition: all 0.3s;
        }
        
        .btn:hover::after {
            left: 100%;
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .desktop-nav { display: none; }
            
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
            
            .empty-cart {
                padding: 60px 20px;
            }
            
            .empty-cart h2 {
                font-size: 24px;
            }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="header">
        <div class="navbar desktop-nav">
            <a href="/">CRONYZO</a>
            <div>
                <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                {% if 'user_id' in session %}
                    <a href="{{ url_for('my_orders') }}">Orders</a>
                    <a href="{{ url_for('account') }}">Account</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}">Login</a>
                {% endif %}
            </div>
        </div>
    </div>
    
    <div class="empty-cart">
        <h2>Your cart is empty</h2>
        <a href="{{ url_for('index') }}" class="btn">Continue Shopping</a>
    </div>
    
    <div class="mobile-nav">
        <a href="{{ url_for('index') }}">
            <i class="fas fa-home"></i>
            <span>Home</span>
        </a>
        
        <a href="{{ url_for('cart') }}">
            <i class="fas fa-shopping-cart"></i>
            <span>Cart</span>
            {% if session.get('cart') %}
            <span class="cart-count">{{ session['cart']|length }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('my_orders') }}">
            <i class="fas fa-box"></i>
            <span>Orders</span>
        </a>
        <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
            <i class="fas fa-user"></i>
            <span>Account</span>
        </a>
    </div>
</body>
</html>
        ''')
    
    cart = session['cart']
    subtotal = sum(item['price'] * item['quantity'] * (1 - item.get('discount', 0)/100) for item in cart.values())
    
    return render_template_string('''
        <!DOCTYPE html>
<html>
<head>
    <title>Your Cart</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
            --danger: #ff4757;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
        }
        
        .header { 
            background: rgba(255,255,255,0.95); 
            padding: 15px; 
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky; 
            top: 0; 
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .container {
            max-width: 1200px;
            margin: 30px auto;
            padding: 0 20px;
        }
        
        h1 {
            color: var(--dark);
            margin-bottom: 30px;
            font-weight: 700;
            position: relative;
            display: inline-block;
        }
        
        h1:after {
            content: '';
            position: absolute;
            bottom: -10px;
            left: 0;
            width: 60px;
            height: 4px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            border-radius: 2px;
        }
        
        .cart-item {
            display: flex;
            gap: 25px;
            margin-bottom: 25px;
            padding: 20px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            position: relative;
        }
        
        .cart-item:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        }
        
        .cart-item-image {
            width: 120px;
            height: 120px;
            object-fit: contain;
            border-radius: 8px;
            background: #f8f9fa;
            padding: 10px;
        }
        
        .cart-item-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        
        .cart-item-title {
            margin: 0 0 10px 0;
            font-size: 18px;
            color: var(--dark);
        }
        
        .price-container {
            display: flex;
            gap: 15px;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .current-price {
            font-weight: bold;
            color: var(--primary);
            font-size: 18px;
        }
        
        .original-price {
            text-decoration: line-through;
            color: #777;
            font-size: 0.9em;
        }
        
        .discount-percent {
            color: var(--danger);
            font-weight: bold;
            font-size: 0.9em;
            background: rgba(255, 71, 87, 0.1);
            padding: 3px 8px;
            border-radius: 12px;
        }
        
        .quantity-form {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .quantity-input {
            padding: 10px;
            width: 70px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            text-align: center;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #ff6b81 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(255, 71, 87, 0.3);
        }
        
        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(255, 71, 87, 0.4);
        }
        
        .summary {
            margin-top: 40px;
            padding: 25px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
        }
        
        .summary p {
            margin: 10px 0;
            font-size: 16px;
        }
        
        .summary strong {
            color: var(--dark);
        }
        
        .checkout-btn {
            display: block;
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #28a745 0%, #218838 100%);
            color: white;
            text-align: center;
            text-decoration: none;
            border-radius: 8px;
            margin-top: 20px;
            font-weight: 600;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .checkout-btn:hover:not(.disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(40, 167, 69, 0.4);
        }
        
        .checkout-btn.disabled {
            background: #ccc;
            cursor: not-allowed;
            box-shadow: none;
        }
        
        .continue-shopping {
            display: inline-block;
            margin-top: 15px;
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s;
        }
        
        .continue-shopping:hover {
            text-decoration: underline;
            color: var(--primary-dark);
        }
        
        .empty-cart {
            text-align: center;
            padding: 50px 0;
        }
        
        .empty-cart i {
            font-size: 60px;
            color: #ddd;
            margin-bottom: 20px;
        }
        
        .empty-cart p {
            color: #777;
            font-size: 18px;
            margin-bottom: 20px;
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .container {
                padding: 0 15px;
            }
            
            .cart-item {
                flex-direction: column;
                gap: 15px;
                padding: 15px;
            }
            
            .cart-item-image {
                width: 100%;
                height: auto;
                max-height: 200px;
            }
            
            .desktop-nav { display: none; }
            
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="header">
        <div class="navbar desktop-nav">
            <a href="/">CRONYZO</a>
            <div>
                <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                {% if 'user_id' in session %}
                    <a href="{{ url_for('my_orders') }}">Orders</a>
                    <a href="{{ url_for('account') }}">Account</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}">Login</a>
                {% endif %}
            </div>
        </div>
    </div>
    
    <div class="container">
        <h1>Your Shopping Cart</h1>
        
        {% if cart.values()|length > 0 %}
            {% for item in cart.values() %}
            <div class="cart-item">
                <img src="{{ url_for('static', filename='images/' + item.image) if item.image else 'https://via.placeholder.com/100' }}" 
                     class="cart-item-image" alt="{{ item.title }}">
                
                <div class="cart-item-content">
                    <div>
                        <h3 class="cart-item-title">{{ item.title }}</h3>
                        <div class="price-container">
                            <span class="current-price">₹{{ "{:,.2f}".format(item.price * (1 - item.get('discount', 0)/100) * item.quantity) }}</span>
                            {% if item.get('discount', 0) > 0 %}
                            <span class="original-price">₹{{ "{:,.2f}".format(item.price * item.quantity) }}</span>
                            <span class="discount-percent">{{ item.get('discount', 0) }}% OFF</span>
                            {% endif %}
                        </div>
                    </div>
                    
                    <div class="quantity-form">
                        <form method="post" action="{{ url_for('update_cart', product_id=item.id) }}">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <input type="number" name="quantity" value="{{ item.quantity }}" min="1" max="{{ item.max_quantity }}" class="quantity-input">
                            <button type="submit" class="btn btn-primary">Update</button>
                        </form>
                        
                        <form method="post" action="{{ url_for('remove_from_cart', product_id=item.id) }}">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" class="btn btn-danger">Remove</button>
                        </form>
                    </div>
                </div>
            </div>
            {% endfor %}
            
            <div class="summary">
                <p><strong>Subtotal:</strong> ₹{{ "{:,.2f}".format(subtotal) }}</p>
                <p>Delivery charge will be calculated at checkout</p>
                
                <a href="{{ url_for('checkout') }}" class="checkout-btn {% if subtotal < 25000 %}disabled{% endif %}">
                    Proceed to Checkout {% if subtotal < 25000 %}(Min ₹25,000){% endif %}
                </a>
                <a href="{{ url_for('index') }}" class="continue-shopping">Continue Shopping</a>
            </div>
        {% else %}
            <div class="empty-cart">
                <i class="fas fa-shopping-cart"></i>
                <p>Your cart is empty</p>
                <a href="{{ url_for('index') }}" class="btn btn-primary">Browse Products</a>
            </div>
        {% endif %}
    </div>
    
    <div class="mobile-nav">
        <a href="{{ url_for('index') }}">
            <i class="fas fa-home"></i>
            <span>Home</span>
        </a>
        
        <a href="{{ url_for('cart') }}">
            <i class="fas fa-shopping-cart"></i>
            <span>Cart</span>
            {% if session.get('cart') %}
            <span class="cart-count">{{ session['cart']|length }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('my_orders') }}">
            <i class="fas fa-box"></i>
            <span>Orders</span>
        </a>
        <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
            <i class="fas fa-user"></i>
            <span>Account</span>
        </a>
    </div>
</body>
</html>
    ''', cart=session['cart'], subtotal=subtotal)

@app.route('/update_cart/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'cart' not in session:
        return redirect(url_for('cart'))
    
    try:
        quantity = int(request.form['quantity'])
        cart = session['cart']
        
        if str(product_id) in cart:
            if quantity <= 0:
                del cart[str(product_id)]
            else:
                cart[str(product_id)]['quantity'] = quantity
            
            session['cart'] = cart
    except Exception as e:
        print(f"Error updating cart: {e}")
    
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'cart' not in session:
        return redirect(url_for('cart'))
    
    cart = session['cart']
    if str(product_id) in cart:
        del cart[str(product_id)]
        session['cart'] = cart
    
    return redirect(url_for('cart'))

@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('index'))
    
    cart = session['cart']
    subtotal = sum(item['price'] * item['quantity'] * (1 - item.get('discount', 0)/100) for item in cart.values())
    
    if subtotal < 25000:
        return redirect(url_for('cart'))
    
    user_profile = get_user_profile(session['user_id'])
    
    return render_template_string('''
        <!DOCTYPE html>
<html>
<head>
    <title>Checkout</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
            --danger: #ff4757;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
        }
        
        .header { 
            background: rgba(255,255,255,0.95); 
            padding: 15px; 
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky; 
            top: 0; 
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .container {
            max-width: 1200px;
            margin: 30px auto;
            padding: 0 20px;
        }
        
        h1 {
            color: var(--dark);
            margin-bottom: 30px;
            font-weight: 700;
            position: relative;
            display: inline-block;
        }
        
        h1:after {
            content: '';
            position: absolute;
            bottom: -10px;
            left: 0;
            width: 60px;
            height: 4px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            border-radius: 2px;
        }
        
        h2 {
            color: var(--dark);
            margin-top: 0;
            margin-bottom: 25px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }
        
        .checkout-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }
        
        .checkout-section {
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #555;
        }
        
        .form-group input,
        .form-group select {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        .form-group input:focus,
        .form-group select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .payment-section {
            margin: 30px 0;
            padding: 25px;
            background: #f5f7fb;
            border-radius: 12px;
        }
        
        .payment-section h3 {
            margin-top: 0;
            color: var(--primary-dark);
        }
        
        .qr-code {
            text-align: center;
            margin: 20px 0;
            padding: 15px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        
        .qr-code img {
            max-width: 200px;
            border-radius: 4px;
        }
        
        .order-summary {
            background: #f9f9f9;
        }
        
        .order-item {
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #eee;
        }
        
        .order-item:last-child {
            border-bottom: none;
        }
        
        .order-total {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-weight: bold;
        }
        
        .payment-summary {
            margin: 20px 0;
            padding: 20px;
            background: #e9f7ef;
            border-radius: 12px;
        }
        
        .payment-summary div {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        
        .payment-summary div:last-child {
            margin-bottom: 0;
        }
        
        .btn {
            display: block;
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-align: center;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .checkout-container {
                grid-template-columns: 1fr;
            }
            
            .container {
                padding: 0 15px;
            }
            
            .desktop-nav { display: none; }
            
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="header">
        <div class="navbar desktop-nav">
            <a href="/">CRONYZO</a>
            <div>
                <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                {% if 'user_id' in session %}
                    <a href="{{ url_for('my_orders') }}">Orders</a>
                    <a href="{{ url_for('account') }}">Account</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}">Login</a>
                {% endif %}
            </div>
        </div>
    </div>
    
    <div class="container">
        <h1>Checkout</h1>
        
        <div class="checkout-container">
            <div class="checkout-section">
                <h2>Shipping Information</h2>
                <form method="post" action="{{ url_for('place_order') }}">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" name="name" value="{{ user_profile['name'] if user_profile and user_profile['name'] else '' }}" required>
                    </div>
                    
                    <div class="form-group">
                        <label>WhatsApp Number</label>
                        <input type="tel" name="phone" value="{{ user_profile['phone'] if user_profile else '' }}" required>
                    </div>
                    
                    <div class="form-group">
                        <label>State</label>
                        <select id="state" name="state" required onchange="updateDeliveryCharge()">
                            <option value="">Select State</option>
                            {% for state in delivery_charges.keys() %}
                            <option value="{{ state }}" {% if user_profile and user_profile['state'] == state %}selected{% endif %}>{{ state }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label>City</label>
                        <select id="city" name="city" required onchange="updateDeliveryCharge()">
                            <option value="">Select City</option>
                            {% if user_profile and user_profile['state'] %}
                                {% for city in delivery_charges[user_profile['state']].keys() %}
                                <option value="{{ city }}" {% if user_profile['city'] == city %}selected{% endif %}>{{ city }}</option>
                                {% endfor %}
                            {% endif %}
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label>Full Address</label>
                        <input type="text" name="address" value="{{ user_profile['address'] if user_profile and user_profile['address'] else '' }}" required>
                    </div>
                    
                    <div class="payment-section">
                        <h3>Advance Payment (50%)</h3>
                        <p>Please pay 50% advance via PhonePe QR code:</p>
                        <div class="qr-code">
                            <img src="{{ url_for('static', filename='images/scaner.png') }}" alt="PhonePe QR Code">
                        </div>
                        <div class="form-group">
                            <label>Transaction ID</label>
                            <input type="text" name="transaction_id" required>
                        </div>
                    </div>
                    
                    <div class="payment-summary">
                        <div id="delivery-charge-display">
                            <span>Delivery Charge:</span>
                            <span>₹0</span>
                        </div>
                        <div id="total-amount-display">
                            <span>Total Amount:</span>
                            <span>₹{{ "{:,.2f}".format(subtotal) }}</span>
                        </div>
                        <div id="advance-payment-display">
                            <span>Advance Payment (50%):</span>
                            <span>₹{{ "{:,.2f}".format(subtotal * 0.5) }}</span>
                        </div>
                    </div>
                    
                    <button type="submit" class="btn">Place Order</button>
                </form>
            </div>
            
            <div class="checkout-section order-summary">
                <h2>Order Summary</h2>
                {% for item in cart.values() %}
                <div class="order-item">
                    <span>{{ item.title }} ({{ item.quantity }} × ₹{{ "{:,.2f}".format(item.price * (1 - item.get('discount', 0)/100)) }})</span>
                    <span>₹{{ "{:,.2f}".format(item.price * (1 - item.get('discount', 0)/100) * item.quantity) }}</span>
                </div>
                {% endfor %}
                
                <div class="order-item order-total">
                    <strong>Subtotal:</strong>
                    <strong>₹{{ "{:,.2f}".format(subtotal) }}</strong>
                </div>
            </div>
        </div>
    </div>
    
    <div class="mobile-nav">
        <a href="{{ url_for('index') }}">
            <i class="fas fa-home"></i>
            <span>Home</span>
        </a>
        
        <a href="{{ url_for('cart') }}">
            <i class="fas fa-shopping-cart"></i>
            <span>Cart</span>
            {% if session.get('cart') %}
            <span class="cart-count">{{ session['cart']|length }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('my_orders') }}">
            <i class="fas fa-box"></i>
            <span>Orders</span>
        </a>
        <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
            <i class="fas fa-user"></i>
            <span>Account</span>
        </a>
    </div>
    
    <script>
        const deliveryCharges = {{ delivery_charges|tojson }};
        const subtotal = {{ subtotal }};
        
        document.getElementById('state').addEventListener('change', function() {
            const state = this.value;
            const citySelect = document.getElementById('city');
            
            citySelect.innerHTML = '<option value="">Select City</option>';
            
            if (state && deliveryCharges[state]) {
                for (const city in deliveryCharges[state]) {
                    const option = document.createElement('option');
                    option.value = city;
                    option.textContent = city;
                    citySelect.appendChild(option);
                }
            }
        });
        
        function updateDeliveryCharge() {
            const state = document.getElementById('state').value;
            const city = document.getElementById('city').value;
            let charge = 0;
            
            if (state && city && deliveryCharges[state] && deliveryCharges[state][city]) {
                charge = deliveryCharges[state][city];
            }
            
            const totalAmount = subtotal + charge;
            const advancePayment = totalAmount * 0.5;
            
            document.getElementById('delivery-charge-display').innerHTML = 
                `<span>Delivery Charge:</span><span>₹${charge.toLocaleString('en-IN')}</span>`;
            document.getElementById('total-amount-display').innerHTML = 
                `<span>Total Amount:</span><span>₹${totalAmount.toLocaleString('en-IN')}</span>`;
            document.getElementById('advance-payment-display').innerHTML = 
                `<span>Advance Payment (50%):</span><span>₹${advancePayment.toLocaleString('en-IN')}</span>`;
        }
        
        // Initialize delivery charge if state/city is pre-selected
        document.addEventListener('DOMContentLoaded', function() {
            const state = document.getElementById('state').value;
            const city = document.getElementById('city').value;
            if (state && city) {
                updateDeliveryCharge();
            }
        });
    </script>
</body>
</html>
    ''', cart=session['cart'], subtotal=subtotal, delivery_charges=DELIVERY_CHARGES, user_profile=user_profile)

@app.route('/place_order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('index'))
    
    try:
        name = request.form['name']
        phone = request.form['phone']
        state = request.form['state']
        city = request.form['city']
        address = request.form['address']
        transaction_id = request.form['transaction_id']
        
        cart = session['cart']
        subtotal = sum(item['price'] * item['quantity'] * (1 - item.get('discount', 0)/100) for item in cart.values())
        delivery_charge = DELIVERY_CHARGES.get(state, {}).get(city, 0)
        total_amount = subtotal + delivery_charge
        advance_payment = total_amount * 0.5
        
        items = ", ".join([f"{item['title']} ({item['quantity']} × ₹{item['price'] * (1 - item.get('discount', 0)/100):,.2f})" for item in cart.values()])
        
        with get_db() as conn:
            c = conn.cursor()
            
            c.execute("SELECT id FROM users WHERE phone = ?", (phone,))
            user = c.fetchone()
            
            if not user:
                c.execute("INSERT INTO users (phone, name, address, state, city) VALUES (?, ?, ?, ?, ?)", 
                         (phone, name, address, state, city))
                conn.commit()
                user_id = c.lastrowid
            else:
                user_id = user[0]
                # Update user profile with latest information
                c.execute("UPDATE users SET name = ?, address = ?, state = ?, city = ? WHERE id = ?",
                         (name, address, state, city, user_id))
                conn.commit()
            
            c.execute('''INSERT INTO orders 
            (order_date, name, phone, state, city, address, 
             transaction_id, subtotal, delivery_charge, 
             total_amount, advance_payment, items, user_id, status, can_cancel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, phone, 
         state, city, address, transaction_id, subtotal, 
         delivery_charge, total_amount, advance_payment, 
         items, user_id, 'Processing', 1))
            
            conn.commit()
            order_id = c.lastrowid
            
            with open('orders.txt', 'a', encoding='utf-8') as f:
                f.write("\n\n=== New Order ===\n")
                f.write(f"Order Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Customer: {name} ({phone})\n")
                f.write(f"Address: {address}, {city}, {state}\n")
                f.write(f"Transaction ID: {transaction_id}\n")
                f.write(f"Subtotal: ₹{subtotal:,.2f}\n")
                f.write(f"Delivery Charge: ₹{delivery_charge:,.2f}\n")
                f.write(f"Total Amount: ₹{total_amount:,.2f}\n")
                f.write(f"Advance Paid: ₹{advance_payment:,.2f}\n")
                f.write("Items:\n")
                for item in cart.values():
                    f.write(f"- {item['title']} ({item['quantity']} × ₹{item['price'] * (1 - item.get('discount', 0)/100):,.2f})\n")
        
        session['user_id'] = user_id
        session['user_phone'] = phone
        
        session.pop('cart', None)
        
        return render_template_string('''
            <!DOCTYPE html>
<html>
<head>
    <title>Order Confirmed</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
            --danger: #ff4757;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
            text-align: center;
        }
        
        .header { 
            background: rgba(255,255,255,0.95); 
            padding: 15px; 
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky; 
            top: 0; 
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .container {
            max-width: 600px;
            margin: 30px auto;
            padding: 0 20px;
        }
        
        .confirmation-icon {
            font-size: 80px;
            color: #28a745;
            margin: 30px 0;
            width: 100px;
            height: 100px;
            background: white;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 5px 20px rgba(40, 167, 69, 0.3);
            animation: bounce 0.5s ease;
        }
        
        @keyframes bounce {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        
        h1 {
            color: var(--dark);
            margin-bottom: 20px;
            font-weight: 700;
        }
        
        p {
            color: #555;
            font-size: 16px;
            line-height: 1.6;
            margin-bottom: 20px;
        }
        
        .order-detail {
            background: white;
            padding: 25px;
            border-radius: 12px;
            margin: 30px 0;
            text-align: left;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
        }
        
        .order-detail h3 {
            margin-top: 0;
            color: var(--dark);
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }
        
        .detail-row {
            display: flex;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #f5f5f5;
        }
        
        .detail-row:last-child {
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }
        
        .detail-label {
            font-weight: bold;
            width: 150px;
            color: #555;
        }
        
        .btn {
            display: inline-block;
            padding: 12px 30px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            margin-top: 20px;
            font-weight: 600;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .redirect-notice {
            margin-top: 15px;
            color: #777;
            font-size: 14px;
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .container {
                padding: 0 15px;
            }
            
            .confirmation-icon {
                font-size: 60px;
                width: 80px;
                height: 80px;
            }
            
            .desktop-nav { display: none; }
            
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script>
        setTimeout(function() {
            window.location.href = "{{ url_for('index') }}";
        }, 8000);
    </script>
</head>
<body>
    <div class="header">
        <div class="navbar desktop-nav">
            <a href="/">CRONYZO</a>
            <div>
                <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                {% if 'user_id' in session %}
                    <a href="{{ url_for('my_orders') }}">Orders</a>
                    <a href="{{ url_for('account') }}">Account</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}">Login</a>
                {% endif %}
            </div>
        </div>
    </div>
    
    <div class="container">
        <div class="confirmation-icon">✓</div>
        <h1>Order Confirmed!</h1>
        <p>Thank you for your purchase. Your order has been placed successfully.</p>
        
        <div class="order-detail">
            <h3>Order Details</h3>
            <div class="detail-row">
                <span class="detail-label">Order Number:</span>
                <span>{{ order_id }}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Customer Name:</span>
                <span>{{ name }}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Phone Number:</span>
                <span>{{ phone }}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Delivery Address:</span>
                <span>{{ address }}, {{ city }}, {{ state }}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Transaction ID:</span>
                <span>{{ transaction_id }}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Total Amount:</span>
                <span>₹{{ "{:,.2f}".format(total_amount) }}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Advance Paid:</span>
                <span>₹{{ "{:,.2f}".format(advance_payment) }}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Delivery Charge:</span>
                <span>₹{{ delivery_charge }}</span>
            </div>
        </div>
        
        <p>We've sent the order details to your WhatsApp number {{ phone }}.</p>
        <p>Our team will contact you shortly for delivery updates.</p>
        
        <a href="{{ url_for('index') }}" class="btn">Continue Shopping</a>
        <p class="redirect-notice">(You will be automatically redirected to home page in 8 seconds)</p>
    </div>
    
    <div class="mobile-nav">
        <a href="{{ url_for('index') }}">
            <i class="fas fa-home"></i>
            <span>Home</span>
        </a>
        
        <a href="{{ url_for('cart') }}">
            <i class="fas fa-shopping-cart"></i>
            <span>Cart</span>
            {% if session.get('cart') %}
            <span class="cart-count">{{ session['cart']|length }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('my_orders') }}">
            <i class="fas fa-box"></i>
            <span>Orders</span>
        </a>
        <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
            <i class="fas fa-user"></i>
            <span>Account</span>
        </a>
    </div>
</body>
</html>
        ''', order_id=order_id, name=name, phone=phone, address=address,
       city=city, state=state, transaction_id=transaction_id,
       total_amount=total_amount, advance_payment=advance_payment,
       delivery_charge=delivery_charge)
    
    except Exception as e:
        print(f"Error placing order: {e}")
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Order Failed</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    
        :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
            --error: #dc3545;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0; 
            padding: 0; 
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
            text-align: center;
        }
        
        .header { 
            background: rgba(255,255,255,0.95); 
            padding: 15px; 
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky; 
            top: 0; 
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .content-container {
            max-width: 600px;
            margin: 50px auto;
            padding: 0 20px;
        }
        
        .error-icon { 
            font-size: 80px; 
            color: var(--error);
            margin: 20px 0;
            animation: pulse 1.5s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.1); }
            100% { transform: scale(1); }
        }
        
        h1 {
            color: var(--dark);
            margin-bottom: 15px;
        }
        
        p {
            color: #555;
            font-size: 18px;
            margin-bottom: 30px;
        }
        
        .btn {
            display: inline-block;
            padding: 12px 30px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .desktop-nav { display: none; }
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
            
            .content-container {
                margin: 30px auto;
            }
            
            .error-icon {
                font-size: 60px;
            }
        }
                </style>
                <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
            </head>
            <body>
                <div class="header">
                    <div class="navbar desktop-nav">
                        <a href="/">CRONYZO</a>
                        <div>
                            
                            <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                            {% if 'user_id' in session %}
                                <a href="{{ url_for('my_orders') }}">Orders</a>
                                <a href="{{ url_for('account') }}">Account</a>
                                <a href="{{ url_for('logout') }}">Logout</a>
                            {% else %}
                                <a href="{{ url_for('login') }}">Login</a>
                            {% endif %}
                        </div>
                    </div>
                </div>
                
                <div class="error-icon">⚠️</div>
                <h1>Order Failed</h1>
                <p>An error occurred while processing your order. Please try again.</p>
                <a href="{{ url_for('cart') }}" class="btn">Back to Cart</a>
                
                <div class="mobile-nav">
                    <a href="{{ url_for('index') }}">
                        <i class="fas fa-home"></i>
                        <span>Home</span>
                    </a>
                    
                    <a href="{{ url_for('cart') }}">
                        <i class="fas fa-shopping-cart"></i>
                        <span>Cart</span>
                        {% if session.get('cart') %}
                        <span class="cart-count">{{ session['cart']|length }}</span>
                        {% endif %}
                    </a>
                    <a href="{{ url_for('my_orders') }}">
                        <i class="fas fa-box"></i>
                        <span>Orders</span>
                    </a>
                    <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
                        <i class="fas fa-user"></i>
                        <span>Account</span>
                    </a>
                </div>
            </body>
            </html>
        ''')
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/my_orders')
def my_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            c.execute('''SELECT id, order_date, status, total_amount, items, can_cancel
                        FROM orders
                        WHERE user_id = ?
                        ORDER BY order_date DESC''', (session['user_id'],))
            
            orders = [{
                'id': row[0],
                'date': row[1],
                'status': row[2],
                'total': row[3],
                'items': row[4],
                'can_cancel': row[5] and can_cancel_order(row[1])
            } for row in c.fetchall()]
            
    except Exception as e:
        print(f"Error fetching orders: {e}")
        orders = []
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>My Orders</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
            --error: #dc3545;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0; 
            padding: 0; 
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
        }
        
        .header { 
            background: rgba(255,255,255,0.95); 
            padding: 15px; 
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky; 
            top: 0; 
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .content-container {
            max-width: 800px;
            margin: 30px auto;
            padding: 0 20px;
        }
        
        h1 {
            color: var(--dark);
            margin-bottom: 10px;
        }
        
        .order-card { 
            background: white; 
            padding: 25px; 
            margin-bottom: 25px; 
            border-radius: 12px; 
            box-shadow: 0 10px 20px rgba(0,0,0,0.08);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            position: relative;
            transform: perspective(500px) translateZ(0);
        }
        
        .order-card:hover {
            transform: perspective(500px) translateZ(10px);
            box-shadow: 0 15px 30px rgba(0,0,0,0.15);
        }
        
        .order-header { 
            display: flex; 
            justify-content: space-between; 
            margin-bottom: 20px; 
            align-items: center;
        }
        
        .order-header h3 {
            margin: 0;
            color: var(--dark);
        }
        
        .status { 
            padding: 6px 15px; 
            border-radius: 20px; 
            font-size: 14px; 
            font-weight: 500;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        
        .status-processing { 
            background: linear-gradient(135deg, #fff3cd 0%, #ffe69c 100%); 
            color: #856404; 
        }
        
        .status-completed { 
            background: linear-gradient(135deg, #d4edda 0%, #b8e0be 100%); 
            color: #155724; 
        }
        
        .status-shipped { 
            background: linear-gradient(135deg, #cce5ff 0%, #a8d0ff 100%); 
            color: #004085; 
        }
        
        .status-cancelled { 
            background: linear-gradient(135deg, #f8d7da 0%, #f5b5ba 100%); 
            color: #721c24; 
        }
        
        .btn { 
            display: inline-block; 
            padding: 12px 30px; 
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white; 
            text-decoration: none; 
            border-radius: 8px; 
            font-weight: 500;
            transition: all 0.3s;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .no-orders { 
            text-align: center; 
            padding: 60px 0; 
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.08);
            margin-bottom: 30px;
        }
        
        .no-orders h2 {
            color: var(--dark);
            margin-bottom: 15px;
        }
        
        .no-orders p {
            color: #666;
            margin-bottom: 25px;
        }
        
        .order-actions { 
            margin-top: 20px; 
            display: flex; 
            gap: 15px; 
        }
        
        .btn-cancel { 
            background: linear-gradient(135deg, var(--error) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-cancel:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .desktop-nav { display: none; }
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
            
            .content-container {
                padding: 0 15px;
            }
            
            .order-card {
                padding: 20px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="header">
                <div class="navbar desktop-nav">
                    <a href="/">CRONYZO</a>
                    <div>
                        
                        <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                        {% if 'user_id' in session %}
                            <a href="{{ url_for('my_orders') }}">Orders</a>
                            <a href="{{ url_for('account') }}">Account</a>
                            <a href="{{ url_for('logout') }}">Logout</a>
                        {% else %}
                            <a href="{{ url_for('login') }}">Login</a>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <h1>My Orders</h1>
            <p>Logged in as: {{ session['user_phone'] }}</p>
            
            {% if not orders %}
                <div class="no-orders">
                    <h2>No orders found</h2>
                    <p>You haven't placed any orders yet.</p>
                    <a href="{{ url_for('index') }}" class="btn">Start Shopping</a>
                </div>
            {% else %}
                {% for order in orders %}
                <div class="order-card">
                    <div class="order-header">
                        <h3>Order #{{ order.id }}</h3>
                        <span class="status status-{{ order.status|lower }}">
                            {{ order.status }}
                        </span>
                    </div>
                    
                    <div style="margin-bottom: 15px;">
                        <p><strong>Date:</strong> {{ order.date }}</p>
                        <p><strong>Total:</strong> ₹{{ "{:,.2f}".format(order.total) }}</p>
                    </div>
                    
                    <div>
                        <p><strong>Items:</strong> {{ order.items }}</p>
                    </div>
                    
                    {% if order.can_cancel %}
                    <div class="order-actions">
                        <form method="post" action="{{ url_for('cancel_order', order_id=order.id) }}">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" class="btn btn-cancel">Cancel Order</button>
                        </form>
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            {% endif %}
            
            <a href="{{ url_for('index') }}" class="btn">Continue Shopping</a>
            
            <div class="mobile-nav">
                <a href="{{ url_for('index') }}">
                    <i class="fas fa-home"></i>
                    <span>Home</span>
                </a>
                
                <a href="{{ url_for('cart') }}">
                    <i class="fas fa-shopping-cart"></i>
                    <span>Cart</span>
                    {% if session.get('cart') %}
                    <span class="cart-count">{{ session['cart']|length }}</span>
                    {% endif %}
                </a>
                <a href="{{ url_for('my_orders') }}">
                    <i class="fas fa-box"></i>
                    <span>Orders</span>
                </a>
                <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
                    <i class="fas fa-user"></i>
                    <span>Account</span>
                </a>
            </div>
        </body>
        </html>
    ''', orders=orders)

@app.route('/cancel_order/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, order_date FROM orders WHERE id = ?", (order_id,))
            order = c.fetchone()
            
            if not order or order['user_id'] != session['user_id']:
                return "Order not found", 404
                
            if not can_cancel_order(order['order_date']):
                return "Cancellation period has expired", 400
                
            c.execute("UPDATE orders SET status = 'Cancelled', can_cancel = 0 WHERE id = ?", (order_id,))
            conn.commit()
            
            return redirect(url_for('my_orders'))
    except Exception as e:
        print(f"Error cancelling order: {e}")
        return "An error occurred", 500

@app.route('/account')
def account():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_profile = get_user_profile(session['user_id'])
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>My Account</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
            --error: #dc3545;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0; 
            padding: 0; 
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
        }
        
        .header { 
            background: rgba(255,255,255,0.95); 
            padding: 15px; 
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky; 
            top: 0; 
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .content-container {
            max-width: 800px;
            margin: 30px auto;
            padding: 0 20px;
        }
        
        .account-container { 
            background: white; 
            padding: 30px; 
            border-radius: 12px; 
            box-shadow: 0 10px 20px rgba(0,0,0,0.08);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        
        .profile-header { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 25px; 
            border-bottom: 1px solid rgba(0,0,0,0.05);
            padding-bottom: 20px;
        }
        
        .profile-header h1 {
            color: var(--dark);
            margin: 0;
        }
        
        .btn { 
            display: inline-block; 
            padding: 12px 25px; 
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white; 
            text-decoration: none; 
            border-radius: 8px; 
            font-weight: 500;
            transition: all 0.3s;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .profile-info { 
            margin-bottom: 30px; 
        }
        
        .profile-info h3 {
            color: var(--dark);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .info-row { 
            display: flex; 
            margin-bottom: 15px; 
            padding: 10px 0;
            border-bottom: 1px solid rgba(0,0,0,0.03);
        }
        
        .info-label { 
            font-weight: 600; 
            width: 150px; 
            color: #555;
        }
        
        .btn-danger { 
            background: linear-gradient(135deg, var(--error) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .account-actions {
            margin-top: 30px;
        }
        
        .account-actions h3 {
            color: var(--dark);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .action-buttons {
            display: flex; 
            gap: 15px; 
            margin-top: 20px;
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .desktop-nav { display: none; }
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
            
            .content-container {
                padding: 0 15px;
            }
            
            .account-container {
                padding: 20px;
            }
            
            .info-row {
                flex-direction: column;
                gap: 5px;
            }
            
            .info-label {
                width: 100%;
            }
            
            .action-buttons {
                flex-direction: column;
                gap: 10px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="header">
                <div class="navbar desktop-nav">
                    <a href="/">CRONYZO</a>
                    <div>
                        
                        <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                        {% if 'user_id' in session %}
                            <a href="{{ url_for('my_orders') }}">Orders</a>
                            <a href="{{ url_for('account') }}">Account</a>
                            <a href="{{ url_for('logout') }}">Logout</a>
                        {% else %}
                            <a href="{{ url_for('login') }}">Login</a>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <div class="account-container">
                <div class="profile-header">
                    <h1>My Account</h1>
                    <a href="{{ url_for('edit_profile') }}" class="btn">Edit Profile</a>
                </div>
                
                <div class="profile-info">
                    <h3>Profile Information</h3>
                    <div class="info-row">
                        <span class="info-label">Name:</span>
                        <span>{{ user_profile['name'] if user_profile and user_profile['name'] else 'Not set' }}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Phone:</span>
                        <span>{{ user_profile['phone'] if user_profile else '' }}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Email:</span>
                        <span>{{ user_profile['email'] if user_profile and user_profile['email'] else 'Not set' }}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Address:</span>
                        <span>
                            {% if user_profile and user_profile['address'] %}
                                {{ user_profile['address'] }}, {{ user_profile['city'] }}, {{ user_profile['state'] }}
                            {% else %}
                                Not set
                            {% endif %}
                        </span>
                    </div>
                </div>
                
                <div>
                    <h3>Account Actions</h3>
                    <div style="display: flex; gap: 10px; margin-top: 20px;">
                        <form method="post" action="{{ url_for('delete_account') }}" onsubmit="return confirm('Are you sure you want to delete your account? This cannot be undone.');">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" class="btn btn-danger">Delete Account</button>
                        </form>
                    </div>
                </div>
            </div>
            
            <div class="mobile-nav">
                <a href="{{ url_for('index') }}">
                    <i class="fas fa-home"></i>
                    <span>Home</span>
                </a>
                
                <a href="{{ url_for('cart') }}">
                    <i class="fas fa-shopping-cart"></i>
                    <span>Cart</span>
                    {% if session.get('cart') %}
                    <span class="cart-count">{{ session['cart']|length }}</span>
                    {% endif %}
                </a>
                <a href="{{ url_for('my_orders') }}">
                    <i class="fas fa-box"></i>
                    <span>Orders</span>
                </a>
                <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
                    <i class="fas fa-user"></i>
                    <span>Account</span>
                </a>
            </div>
        </body>
        </html>
    ''', user_profile=user_profile)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_profile = get_user_profile(session['user_id'])
    
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        address = request.form.get('address', '')
        state = request.form.get('state', '')
        city = request.form.get('city', '')
        
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute('''UPDATE users 
                            SET name = ?, email = ?, address = ?, state = ?, city = ?
                            WHERE id = ?''',
                         (name, email, address, state, city, session['user_id']))
                conn.commit()
                
                return redirect(url_for('account'))
        except Exception as e:
            print(f"Error updating profile: {e}")
            return "An error occurred", 500
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Edit Profile</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
            --error: #dc3545;
            --secondary: #6c757d;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0; 
            padding: 0; 
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
        }
        
        .header { 
            background: rgba(255,255,255,0.95); 
            padding: 15px; 
            box-shadow: 0 4px 30px rgba(0,0,0,0.1);
            position: sticky; 
            top: 0; 
            z-index: 1000;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
        }
        
        .navbar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            max-width: 1200px; 
            margin: 0 auto; 
        }
        
        .navbar a {
            text-decoration: none;
            color: var(--dark);
            font-weight: 500;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .navbar a:first-child {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .navbar a:hover {
            color: var(--primary);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .content-container {
            max-width: 800px;
            margin: 30px auto;
            padding: 0 20px;
        }
        
        .edit-form { 
            background: white; 
            padding: 30px; 
            border-radius: 12px; 
            box-shadow: 0 10px 20px rgba(0,0,0,0.08);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        
        .edit-form h1 {
            color: var(--dark);
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .form-group { 
            margin-bottom: 20px; 
        }
        
        .form-group label { 
            display: block; 
            margin-bottom: 8px; 
            font-weight: 600; 
            color: #555;
        }
        
        .form-group input, 
        .form-group select { 
            width: 100%; 
            padding: 12px 15px; 
            border: 1px solid #e0e0e0; 
            border-radius: 8px; 
            font-size: 16px;
            transition: all 0.3s;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        
        .form-group input:focus, 
        .form-group select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .btn { 
            display: inline-block; 
            padding: 12px 25px; 
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white; 
            text-decoration: none; 
            border: none;
            border-radius: 8px; 
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-secondary { 
            background: linear-gradient(135deg, var(--secondary) 0%, #5a6268 100%);
            box-shadow: 0 4px 15px rgba(108, 117, 125, 0.3);
        }
        
        .btn-secondary:hover {
            box-shadow: 0 6px 20px rgba(108, 117, 125, 0.4);
        }
        
        .form-actions { 
            margin-top: 30px; 
            display: flex; 
            gap: 15px; 
        }
        
        .mobile-nav { display: none; }
        
        @media (max-width: 768px) {
            .desktop-nav { display: none; }
            .mobile-nav { 
                display: flex; 
                position: fixed; 
                bottom: 0; 
                left: 0; 
                right: 0; 
                background: rgba(255,255,255,0.95); 
                box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
                justify-content: space-around;
                padding: 15px 0;
                z-index: 1000;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                backdrop-filter: blur(10px);
            }
            
            .mobile-nav a {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-decoration: none;
                color: #555;
                font-size: 12px;
                padding: 5px 15px;
                border-radius: 15px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover {
                color: var(--primary);
                background: rgba(67, 97, 238, 0.1);
                transform: translateY(-5px);
            }
            
            .mobile-nav i {
                font-size: 20px;
                margin-bottom: 5px;
                transition: all 0.3s;
            }
            
            .mobile-nav a:hover i {
                transform: scale(1.2);
            }
            
            body { padding-bottom: 80px; }
            
            .content-container {
                padding: 0 15px;
            }
            
            .edit-form {
                padding: 20px;
            }
            
            .form-actions {
                flex-direction: column;
                gap: 10px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="header">
                <div class="navbar desktop-nav">
                    <a href="/">CRONYZO</a>
                    <div>
                        
                        <a href="{{ url_for('cart') }}">Cart (<span class="cart-count">{{ session.get('cart', {})|length }}</span>)</a>
                        {% if 'user_id' in session %}
                            <a href="{{ url_for('my_orders') }}">Orders</a>
                            <a href="{{ url_for('account') }}">Account</a>
                            <a href="{{ url_for('logout') }}">Logout</a>
                        {% else %}
                            <a href="{{ url_for('login') }}">Login</a>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <div class="edit-form">
                <h1>Edit Profile</h1>
                
                <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    
                    <div class="form-group">
                        <label for="name">Full Name</label>
                        <input type="text" id="name" name="name" value="{{ user_profile['name'] if user_profile and user_profile['name'] else '' }}">
                    </div>
                    
                    <div class="form-group">
                        <label for="email">Email</label>
                        <input type="email" id="email" name="email" value="{{ user_profile['email'] if user_profile and user_profile['email'] else '' }}">
                    </div>
                    
                    <div class="form-group">
                        <label for="address">Address</label>
                        <input type="text" id="address" name="address" value="{{ user_profile['address'] if user_profile and user_profile['address'] else '' }}">
                    </div>
                    
                    <div class="form-group">
                        <label for="state">State</label>
                        <select id="state" name="state" onchange="updateCities()">
                            <option value="">Select State</option>
                            {% for state in delivery_charges.keys() %}
                            <option value="{{ state }}" {% if user_profile and user_profile['state'] == state %}selected{% endif %}>{{ state }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="city">City</label>
                        <select id="city" name="city">
                            <option value="">Select City</option>
                            {% if user_profile and user_profile['state'] %}
                                {% for city in delivery_charges[user_profile['state']].keys() %}
                                <option value="{{ city }}" {% if user_profile['city'] == city %}selected{% endif %}>{{ city }}</option>
                                {% endfor %}
                            {% endif %}
                        </select>
                    </div>
                    
                    <div style="margin-top: 20px; display: flex; gap: 10px;">
                        <button type="submit" class="btn">Save Changes</button>
                        <a href="{{ url_for('account') }}" class="btn btn-secondary">Cancel</a>
                    </div>
                </form>
            </div>
            
            <div class="mobile-nav">
                <a href="{{ url_for('index') }}">
                    <i class="fas fa-home"></i>
                    <span>Home</span>
                </a>
                
                <a href="{{ url_for('cart') }}">
                    <i class="fas fa-shopping-cart"></i>
                    <span>Cart</span>
                    {% if session.get('cart') %}
                    <span class="cart-count">{{ session['cart']|length }}</span>
                    {% endif %}
                </a>
                <a href="{{ url_for('my_orders') }}">
                    <i class="fas fa-box"></i>
                    <span>Orders</span>
                </a>
                <a href="{{ url_for('account') if 'user_id' in session else url_for('login') }}">
                    <i class="fas fa-user"></i>
                    <span>Account</span>
                </a>
            </div>
            
            <script>
                const deliveryCharges = {{ delivery_charges|tojson }};
                
                function updateCities() {
                    const state = document.getElementById('state').value;
                    const citySelect = document.getElementById('city');
                    
                    citySelect.innerHTML = '<option value="">Select City</option>';
                    
                    if (state && deliveryCharges[state]) {
                        for (const city in deliveryCharges[state]) {
                            const option = document.createElement('option');
                            option.value = city;
                            option.textContent = city;
                            citySelect.appendChild(option);
                        }
                    }
                }
            </script>
        </body>
        </html>
    ''', user_profile=user_profile, delivery_charges=DELIVERY_CHARGES)

@app.route('/delete_account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            # Delete user's orders first to maintain foreign key constraint
            c.execute("DELETE FROM orders WHERE user_id = ?", (session['user_id'],))
            # Then delete the user
            c.execute("DELETE FROM users WHERE id = ?", (session['user_id'],))
            conn.commit()
            
            session.clear()
            return redirect(url_for('index'))
    except Exception as e:
        print(f"Error deleting account: {e}")
        return "An error occurred while deleting your account", 500

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return {'error': 'No file part'}, 400
    file = request.files['file']
    if file.filename == '':
        return {'error': 'No selected file'}, 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return {'filename': filename}, 200
    return {'error': 'Invalid file type'}, 400

@app.route('/product/fullscreen/<int:product_id>')
def product_fullscreen(product_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = c.fetchone()
    except Exception as e:
        print(f"Error fetching product: {e}")
        return "Product not found", 404
    
    if not product:
        return "Product not found", 404
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>{{ product[1] }} - Full Screen</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
        }
        
        body { 
            margin: 0; 
            padding: 0; 
            background: rgba(0,0,0,0.95);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            overflow: hidden;
            touch-action: none;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }
        
        .image-container {
            position: relative;
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
        }
        
        .fullscreen-image {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            transition: transform 0.3s ease;
            transform-origin: center center;
            cursor: grab;
            user-select: none;
            -webkit-user-drag: none;
        }
        
        .fullscreen-image.grabbing {
            cursor: grabbing;
        }
        
        .control-bar {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 15px;
            background: rgba(0,0,0,0.7);
            padding: 12px 20px;
            border-radius: 50px;
            backdrop-filter: blur(10px);
            z-index: 100;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }
        
        .control-btn {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: rgba(255,255,255,0.1);
            color: white;
            border: none;
            display: flex;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .control-btn:hover {
            background: var(--primary);
            transform: scale(1.1);
        }
        
        .control-btn:active {
            transform: scale(0.95);
        }
        
        .close-btn {
            position: fixed;
            top: 20px;
            right: 20px;
            width: 50px;
            height: 50px;
            background: rgba(255,255,255,0.1);
            color: white;
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            z-index: 100;
            backdrop-filter: blur(10px);
            border: none;
            transition: all 0.3s;
        }
        
        .close-btn:hover {
            background: var(--accent);
            transform: rotate(90deg);
        }
        
        .zoom-level {
            position: fixed;
            top: 20px;
            left: 20px;
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 14px;
            backdrop-filter: blur(10px);
            z-index: 100;
        }
        
        @media (max-width: 768px) {
            .control-bar {
                bottom: 10px;
                padding: 10px 15px;
                gap: 10px;
            }
            
            .control-btn {
                width: 36px;
                height: 36px;
                font-size: 14px;
            }
            
            .close-btn {
                width: 44px;
                height: 44px;
                top: 15px;
                right: 15px;
            }
            
            .zoom-level {
                top: 15px;
                left: 15px;
                font-size: 12px;
                padding: 6px 12px;
            }
        }
            </style>
        </head>
        <body>
            <img src="{{ url_for('static', filename='images/' + product[4]) }}" 
                 class="fullscreen-image" 
                 onclick="window.close()"
                 alt="{{ product[1] }}">
        </body>
        </html>
    ''', product=product)

# Add this at the end of your app.py file, before the if __name__ == '__main__':

# ==================== ADMIN PANEL ====================

# Add this after imports (before routes)
ADMIN_CREDENTIALS = {
    "username": "cronyzo_admin",  # CHANGE THIS
    "password": "Admin@1234"      # CHANGE THIS
}

admin_click_count = 0
last_click_time = 0


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function
# Add these routes anywhere between existing routes
@app.route('/hidden-admin', methods=['GET'])
def hidden_admin():
    global admin_click_count, last_click_time
    
    current_time = time.time()
    if current_time - last_click_time > 5:  # 5 second reset
        admin_click_count = 0
    
    admin_click_count += 1
    last_click_time = current_time
    
    if admin_click_count >= 5:
        admin_click_count = 0
        # Return the admin login page with CSRF token
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Admin Login</title>
                <style>:root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffba08;
        }
        
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .login-form { 
            background: rgba(255,255,255,0.95); 
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 450px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
            transform: perspective(500px) translateZ(0);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        
        .login-form:hover {
            transform: perspective(500px) translateZ(10px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        }
        
        .login-form h2 {
            color: var(--primary-dark);
            text-align: center;
            margin-bottom: 30px;
            font-size: 28px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .form-group { 
            margin-bottom: 25px; 
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: var(--dark);
        }
        
        .form-group input {
            width: 100%;
            padding: 14px 20px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            background: rgba(255,255,255,0.8);
            transition: all 0.3s;
            box-sizing: border-box;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .btn {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border: none;
            padding: 14px;
            width: 100%;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            margin-top: 10px;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        @media (max-width: 768px) {
            .login-form {
                padding: 30px 20px;
                margin: 20px;
            }
        }
                                      </style>
            </head>
            <body>
                <div class="login-form">
                    <h2>Admin Login</h2>
                    <form method="post" action="/admin/verify">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <div class="form-group">
                            <label>Username</label>
                            <input type="text" name="username" required>
                        </div>
                        <div class="form-group">
                            <label>Password</label>
                            <input type="password" name="password" required>
                        </div>
                        <button type="submit" class="btn">Login</button>
                    </form>
                </div>
            </body>
            </html>
        ''')
    
    return jsonify({"status": f"Need {5-admin_click_count} more clicks"}), 200

@app.route('/admin/verify', methods=['POST'])
def verify_admin():
    if request.form['username'] == ADMIN_CREDENTIALS["username"] and \
       request.form['password'] == ADMIN_CREDENTIALS["password"]:
        
        session['admin_logged_in'] = True
        session['admin_token'] = secrets.token_urlsafe(32)  # Generate secure token
        return redirect(url_for('admin_dashboard'))  # Make sure this redirects to admin dashboard
        
    return "Invalid credentials", 401

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Verify credentials
        if (username == ADMIN_USERNAME and 
            check_password_hash(ADMIN_PASSWORD_HASH, password)):
            
            # Generate secure session token
            session['admin_logged_in'] = True
            session['admin_token'] = secrets.token_urlsafe(32)
            session['admin_last_activity'] = datetime.now().isoformat()
            
            # Set secure admin session cookie
            resp = redirect(url_for('admin_dashboard'))
            resp.set_cookie(
                'admin_session',
                value=session['admin_token'],
                httponly=True,
                secure=True,
                samesite='Strict',
                max_age=timedelta(hours=2)
            )
            return resp
        
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Admin Login - CRONYZO</title>
                <style>
                    :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --error: #dc3545;
        }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .login-form {
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 15px 30px rgba(0,0,0,0.08);
            width: 100%;
            max-width: 400px;
            transition: all 0.3s ease;
        }
        
        .login-form:hover {
            box-shadow: 0 20px 40px rgba(0,0,0,0.12);
        }
        
        .login-form h2 {
            text-align: center;
            margin-bottom: 25px;
            color: var(--primary-dark);
            font-size: 28px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--dark);
        }
        
        .form-group input {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 600;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .error {
            color: var(--error);
            margin-top: 15px;
            text-align: center;
            font-size: 14px;
        }
                </style>
            </head>
            <body>
                <div class="login-form">
                    <h2 style="text-align: center; margin-bottom: 25px;">Admin Login</h2>
                    <form method="post">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <div class="form-group">
                            <label for="username">Username</label>
                            <input type="text" id="username" name="username" required>
                        </div>
                        <div class="form-group">
                            <label for="password">Password</label>
                            <input type="password" id="password" name="password" required>
                        </div>
                        <button type="submit" class="btn">Login</button>
                        <p class="error">Invalid credentials. Please try again.</p>
                    </form>
                </div>
                
            </body>
            </html>
        ''')
    
    # Hide admin login page from unauthorized access
    if not request.args.get('secret') == secrets.token_urlsafe(16):
        
        abort(404)
    print("Admin Secret Token:", secrets.token_urlsafe(16))
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Login - CRONYZO</title>
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
        }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .login-form {
            background: rgba(255,255,255,0.95);
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        
        .login-form:hover {
            transform: perspective(500px) translateZ(10px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        }
        
        .login-form h2 {
            text-align: center;
            margin-bottom: 25px;
            font-size: 28px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--dark);
        }
        
        .form-group input {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s;
            background: rgba(255,255,255,0.8);
        }
        
        .form-group input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 600;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
            </style>
        </head>
        <body>
            <div class="login-form">
                <h2 style="text-align: center; margin-bottom: 25px;">Admin Login</h2>
                <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <div class="form-group">
                        <label for="username">Username</label>
                        <input type="text" id="username" name="username" required>
                    </div>
                    <div class="form-group">
                        <label for="password">Password</label>
                        <input type="password" id="password" name="password" required>
                    </div>
                    <button type="submit" class="btn">Login</button>
                </form>
            </div>
        </body>
        </html>
    ''')

@app.route('/admin/logout')
@admin_required
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_token', None)
    session.pop('admin_last_activity', None)
    resp = redirect(url_for('index'))
    resp.set_cookie('admin_session', '', expires=0)
    return resp

@app.route('/admin')
@admin_required  # Make sure you have this decorator
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_logout'))
    
    # Update last activity
    session['admin_last_activity'] = datetime.now().isoformat()
    
    try:
        with get_db() as conn:
            # Get stats for dashboard
            c = conn.cursor()
            
            # Total products
            c.execute("SELECT COUNT(*) FROM products")
            total_products = c.fetchone()[0]
            
            # Total orders
            c.execute("SELECT COUNT(*) FROM orders")
            total_orders = c.fetchone()[0]
            
            # Total users
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            
            # Recent orders
            c.execute("""
                SELECT o.id, o.order_date, o.status, o.total_amount, u.name, u.phone 
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.id
                ORDER BY o.order_date DESC
                LIMIT 5
            """)
            recent_orders = c.fetchall()
            
            # Low stock products
            c.execute("SELECT id, title, stock FROM products WHERE stock < 10 ORDER BY stock ASC LIMIT 5")
            low_stock = c.fetchall()
            
    except Exception as e:
        print(f"Error fetching dashboard data: {e}")
        total_products = 0
        total_orders = 0
        total_users = 0
        recent_orders = []
        low_stock = []
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Dashboard - CRONYZO</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .stats-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 25px;
            margin-bottom: 35px;
        }
        
        .stat-card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 30px rgba(0,0,0,0.1);
        }
        
        .stat-card h3 {
            margin-top: 0;
            color: #666;
            font-size: 16px;
            font-weight: 500;
        }
        
        .stat-card p {
            font-size: 32px;
            margin: 15px 0 0;
            font-weight: bold;
            color: var(--primary);
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, var(--success) 0%, #1e7e34 100%);
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
        }
        
        .table th {
            background: rgba(248, 249, 250, 0.8);
            font-weight: 600;
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .table td {
            padding: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .table tr:hover {
            background: rgba(248, 250, 255, 0.8);
        }
        
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-processing {
            background: rgba(255, 243, 205, 0.8);
            color: #856404;
        }
        
        .status-completed {
            background: rgba(212, 237, 218, 0.8);
            color: #155724;
        }
        
        .status-shipped {
            background: rgba(204, 229, 255, 0.8);
            color: #004085;
        }
        
        .status-cancelled {
            background: rgba(248, 215, 218, 0.8);
            color: #721c24;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .badge-warning {
            background: rgba(255, 193, 7, 0.8);
            color: #333;
        }
        
        .badge-danger {
            background: rgba(220, 53, 69, 0.8);
            color: white;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
        }
        
        .form-control, .form-select {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            background: rgba(255,255,255,0.8);
            transition: all 0.3s;
        }
        
        .form-control:focus, .form-select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .text-right {
            text-align: right;
        }
        
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 25px;
        }
        
        .alert-success {
            background: rgba(212, 237, 218, 0.8);
            color: #155724;
        }
        
        .alert-danger {
            background: rgba(248, 215, 218, 0.8);
            color: #721c24;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}" class="active"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="stats-container">
                        <div class="stat-card">
                            <h3>Total Products</h3>
                            <p>{{ total_products }}</p>
                        </div>
                        <div class="stat-card">
                            <h3>Total Orders</h3>
                            <p>{{ total_orders }}</p>
                        </div>
                        <div class="stat-card">
                            <h3>Total Users</h3>
                            <p>{{ total_users }}</p>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-header">
                            <h2>Recent Orders</h2>
                            <a href="{{ url_for('admin_orders') }}" class="btn btn-sm">View All</a>
                        </div>
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Order ID</th>
                                    <th>Date</th>
                                    <th>Customer</th>
                                    <th>Amount</th>
                                    <th>Status</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for order in recent_orders %}
                                <tr>
                                    <td>#{{ order[0] }}</td>
                                    <td>{{ order[1] }}</td>
                                    <td>{{ order[4] or 'Guest' }} ({{ order[5] }})</td>
                                    <td>₹{{ "{:,.2f}".format(order[3]) }}</td>
                                    <td>
                                        <span class="status-badge status-{{ order[2]|lower }}">
                                            {{ order[2] }}
                                        </span>
                                    </td>
                                    <td>
                                        <a href="{{ url_for('admin_order_detail', order_id=order[0]) }}" class="btn btn-sm">
                                            <i class="fas fa-eye"></i> View
                                        </a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    
                    <div class="card">
                        <div class="card-header">
                            <h2>Low Stock Products</h2>
                            <a href="{{ url_for('admin_products') }}" class="btn btn-sm">View All</a>
                        </div>
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Product ID</th>
                                    <th>Product Name</th>
                                    <th>Stock</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for product in low_stock %}
                                <tr>
                                    <td>#{{ product[0] }}</td>
                                    <td>{{ product[1] }}</td>
                                    <td>
                                        <span class="badge {% if product[2] < 5 %}badge-danger{% else %}badge-warning{% endif %}">
                                            {{ product[2] }} left
                                        </span>
                                    </td>
                                    <td>
                                        <a href="{{ url_for('admin_edit_product', product_id=product[0]) }}" class="btn btn-sm">
                                            <i class="fas fa-edit"></i> Edit
                                        </a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', total_products=total_products, total_orders=total_orders, 
       total_users=total_users, recent_orders=recent_orders, low_stock=low_stock)

@app.route('/admin/products')
@admin_required
def admin_products():
    search_query = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            query = "SELECT * FROM products"
            params = []
            
            if search_query or category_filter:
                query += " WHERE "
                conditions = []
                
                if search_query:
                    conditions.append("(title LIKE ? OR description LIKE ? OR tags LIKE ?)")
                    params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
                
                if category_filter:
                    if search_query:
                        conditions.append("AND")
                    conditions.append("category = ?")
                    params.append(category_filter)
                
                query += " ".join(conditions)
            
            query += " ORDER BY id DESC"
            c.execute(query, params)
            products = c.fetchall()
            
            # Get all categories for filter
            c.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != ''")
            categories = [row[0] for row in c.fetchall()]
            
    except Exception as e:
        print(f"Error fetching products: {e}")
        products = []
        categories = []
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Manage Products - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, var(--success) 0%, #1e7e34 100%);
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .btn-success:hover {
            box-shadow: 0 6px 20px rgba(40, 167, 69, 0.4);
        }
        
        .search-form {
            display: flex;
            gap: 15px;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }
        
        .search-form input, 
        .search-form select {
            flex: 1;
            min-width: 200px;
            padding: 12px 15px;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            background: rgba(255,255,255,0.8);
            transition: all 0.3s;
        }
        
        .search-form input:focus, 
        .search-form select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
        }
        
        .table th {
            background: rgba(248, 249, 250, 0.8);
            font-weight: 600;
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .table td {
            padding: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .table tr:hover {
            background: rgba(248, 250, 255, 0.8);
        }
        
        .badge {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .badge-success {
            background: rgba(40, 167, 69, 0.8);
            color: white;
        }
        
        .badge-warning {
            background: rgba(255, 193, 7, 0.8);
            color: #333;
        }
        
        .badge-danger {
            background: rgba(220, 53, 69, 0.8);
            color: white;
        }
        
        .product-image {
    width: 100%;
    height: 200px;
    object-fit: contain;
    cursor: pointer;
    background: #f5f5f5;
    border-radius: 5px;
}

.additional-images-preview img {
    transition: transform 0.2s;
}

.additional-images-preview img:hover {
    transform: scale(1.1);
    z-index: 1;
}
        
        .product-image:hover {
            transform: scale(1.1);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        
        .actions-container {
            display: flex;
            gap: 8px;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
            
            .search-form {
                flex-direction: column;
                gap: 10px;
            }
            
            .search-form input,
            .search-form select,
            .search-form button {
                width: 100%;
            }
            
            .table {
                display: block;
                overflow-x: auto;
            }
            
            .actions-container {
                flex-direction: column;
                gap: 5px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}" class="active"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>Manage Products</h2>
                            <a href="{{ url_for('admin_add_product') }}" class="btn btn-success">
                                <i class="fas fa-plus"></i> Add Product
                            </a>
                        </div>
                        
                        <form method="get" class="search-form">
                            <input type="text" name="search" placeholder="Search products..." value="{{ search_query }}">
                            <select name="category">
                                <option value="">All Categories</option>
                                {% for category in categories %}
                                <option value="{{ category }}" {% if category_filter == category %}selected{% endif %}>{{ category }}</option>
                                {% endfor %}
                            </select>
                            <button type="submit" class="btn">
                                <i class="fas fa-search"></i> Search
                            </button>
                            <a href="{{ url_for('admin_products') }}" class="btn btn-danger">
                                <i class="fas fa-times"></i> Clear
                            </a>
                        </form>
                        
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Image</th>
                                    <th>Title</th>
                                    <th>Price</th>
                                    <th>Stock</th>
                                    <th>Category</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for product in products %}
                                <tr>
                                    <td>#{{ product[0] }}</td>
                                    <td>
                                        <img src="{{ url_for('static', filename='images/' + product[4]) if product[4] else 'https://via.placeholder.com/60' }}" 
                                             class="product-image" alt="{{ product[1] }}">
                                    </td>
                                    <td>{{ product[1] }}</td>
                                    <td>₹{{ "{:,.2f}".format(product[3]) }}</td>
                                    <td>
                                        <span class="badge {% if product[9] > 20 %}badge-success{% elif product[9] > 5 %}badge-warning{% else %}badge-danger{% endif %}">
                                            {{ product[9] }} in stock
                                        </span>
                                    </td>
                                    <td>{{ product[12] or '-' }}</td>
                                    <td>
                                        <a href="{{ url_for('admin_edit_product', product_id=product[0]) }}" class="btn btn-sm">
                                            <i class="fas fa-edit"></i> Edit
                                        </a>
                                        <form method="post" action="{{ url_for('admin_delete_product', product_id=product[0]) }}" style="display: inline;">
                                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                            <button type="submit" class="btn btn-sm btn-danger" onclick="return confirm('Are you sure you want to delete this product?');">
                                                <i class="fas fa-trash"></i> Delete
                                            </button>
                                        </form>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', products=products, search_query=search_query, 
       category_filter=category_filter, categories=categories)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    if request.method == 'POST':
        try:
            title = request.form['title']
            description = request.form['description']
            price = float(request.form['price'])
            image = request.form['image']
            min_quantity = int(request.form['min_quantity'])
            max_quantity = int(request.form['max_quantity'])
            discount = int(request.form['discount'])
            rating = float(request.form['rating'])
            stock = int(request.form['stock'])
            images = request.form['images']
            youtube_url = request.form['youtube_url']
            category = request.form['category']
            tags = request.form['tags']
            
            # Validate data
            if not title or not price:
                raise ValueError("Title and price are required")
            
            with get_db() as conn:
                c = conn.cursor()
                c.execute('''INSERT INTO products 
                            (title, description, price, image, min_quantity, max_quantity, 
                             discount, rating, stock, images, youtube_url, category, tags)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (title, description, price, image, min_quantity, max_quantity,
                          discount, rating, stock, images, youtube_url, category, tags))
                conn.commit()
                
                return redirect(url_for('admin_products'))
        
        except Exception as e:
            print(f"Error adding product: {e}")
            error = str(e)
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Add Product - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, var(--success) 0%, #1e7e34 100%);
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .btn-success:hover {
            box-shadow: 0 6px 20px rgba(40, 167, 69, 0.4);
        }
        
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 25px;
            transition: all 0.3s;
        }
        
        .alert-danger {
            background: rgba(248, 215, 218, 0.9);
            color: #721c24;
            border-left: 4px solid var(--danger);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--dark);
        }
        
        .form-control, .form-select, textarea {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            background: rgba(255,255,255,0.8);
            transition: all 0.3s;
            font-family: inherit;
        }
        
        .form-control:focus, .form-select:focus, textarea:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .file-input-wrapper {
            margin-bottom: 20px;
        }
        
        .file-input-label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--dark);
        }
        
        .file-input-info {
            font-size: 13px;
            color: #666;
            margin-top: 5px;
        }
        
        .image-preview {
            max-width: 200px;
            max-height: 200px;
            margin-top: 15px;
            border-radius: 8px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
            display: none;
            transition: all 0.3s;
        }
        
        .additional-images-preview {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin-top: 15px;
        }
        
        .additional-image-preview {
            max-width: 120px;
            max-height: 120px;
            border-radius: 8px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
            transition: all 0.3s;
        }
        
        .additional-image-preview:hover {
            transform: scale(1.05);
            box-shadow: 0 6px 15px rgba(0,0,0,0.15);
        }
        
        .text-right {
            text-align: right;
            margin-top: 30px;
        }
        
        small {
            font-size: 12px;
            color: #666;
            display: block;
            margin-top: 5px;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
            
            .card-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 15px;
            }
            
            .image-preview {
                max-width: 150px;
            }
            
            .additional-image-preview {
                max-width: 80px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}" class="active"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>Add New Product</h2>
                            <a href="{{ url_for('admin_products') }}" class="btn">
                                <i class="fas fa-arrow-left"></i> Back to Products
                            </a>
                        </div>
                        
                        {% if error %}
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-circle"></i> {{ error }}
                        </div>
                        {% endif %}
                        
                        <form method="post" enctype="multipart/form-data">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            
                            <div class="form-group">
                                <label for="title">Product Title</label>
                                <input type="text" id="title" name="title" class="form-control" required>
                            </div>
                            
                            <div class="form-group">
                                <label for="description">Description</label>
                                <textarea id="description" name="description" class="form-control" rows="4"></textarea>
                            </div>
                            
                            <div class="form-group">
                                <label for="price">Price (₹)</label>
                                <input type="number" id="price" name="price" class="form-control" step="0.01" min="0" required>
                                                        </div>
                            
                            <div class="form-group">
                                <label for="image">Main Image URL</label>
                                <input type="text" id="image" name="image" class="form-control">
                                <small>Enter the filename (e.g. product1.jpg) - upload the file to static/images first</small>
                            </div>
                            
                            <div class="form-group">
                                <label for="min_quantity">Minimum Quantity</label>
                                <input type="number" id="min_quantity" name="min_quantity" class="form-control" min="1" value="1">
                            </div>
                            
                            <div class="form-group">
                                <label for="max_quantity">Maximum Quantity</label>
                                <input type="number" id="max_quantity" name="max_quantity" class="form-control" min="1" value="10">
                            </div>
                            
                            <div class="form-group">
                                <label for="discount">Discount (%)</label>
                                <input type="number" id="discount" name="discount" class="form-control" min="0" max="100" value="0">
                            </div>
                            
                            <div class="form-group">
                                <label for="rating">Rating (0-5)</label>
                                <input type="number" id="rating" name="rating" class="form-control" min="0" max="5" step="0.1" value="0">
                            </div>
                            
                            <div class="form-group">
                                <label for="stock">Stock Quantity</label>
                                <input type="number" id="stock" name="stock" class="form-control" min="0" value="100">
                            </div>
                            
                            <div class="form-group">
                                <label for="images">Additional Images (JSON array)</label>
                                <textarea id="images" name="images" class="form-control" rows="2" placeholder='["image1.jpg", "image2.jpg"]'></textarea>
                                <small>Enter as JSON array of filenames</small>
                            </div>
                            
                            <div class="form-group">
                                <label for="youtube_url">YouTube URL</label>
                                <input type="url" id="youtube_url" name="youtube_url" class="form-control" placeholder="https://youtu.be/...">
                            </div>
                            
                            <div class="form-group">
                                <label for="category">Category</label>
                                <input type="text" id="category" name="category" class="form-control">
                            </div>
                            
                            <div class="form-group">
                                <label for="tags">Tags (JSON array)</label>
                                <textarea id="tags" name="tags" class="form-control" rows="2" placeholder='["tag1", "tag2"]'></textarea>
                                <small>Enter as JSON array of tags</small>
                            </div>
                            
                            <div class="text-right">
                                <button type="submit" class="btn btn-success">
                                    <i class="fas fa-save"></i> Save Product
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', error=error if 'error' in locals() else None)

@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(product_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            if request.method == 'POST':
                title = request.form['title']
                description = request.form['description']
                price = float(request.form['price'])
                image = request.form['image']
                min_quantity = int(request.form['min_quantity'])
                max_quantity = int(request.form['max_quantity'])
                discount = int(request.form['discount'])
                rating = float(request.form['rating'])
                stock = int(request.form['stock'])
                images = request.form['images']
                youtube_url = request.form['youtube_url']
                category = request.form['category']
                tags = request.form['tags']
                
                c.execute('''UPDATE products SET
                            title = ?, description = ?, price = ?, image = ?,
                            min_quantity = ?, max_quantity = ?, discount = ?,
                            rating = ?, stock = ?, images = ?, youtube_url = ?,
                            category = ?, tags = ?
                            WHERE id = ?''',
                         (title, description, price, image, min_quantity, max_quantity,
                          discount, rating, stock, images, youtube_url, category, tags,
                          product_id))
                conn.commit()
                
                return redirect(url_for('admin_products'))
            
            c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = c.fetchone()
            
            if not product:
                return "Product not found", 404
                
    except Exception as e:
        print(f"Error editing product: {e}")
        error = str(e)
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Edit Product - CRONYZO Admin</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                   :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 25px;
        }
        
        .alert-danger {
            background: rgba(248, 215, 218, 0.8);
            color: #721c24;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
        }
                </style>
                <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
            </head>
            <body>
                <div class="admin-header">
                    <h1>CRONYZO Admin</h1>
                    <div>
                        <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                            <i class="fas fa-sign-out-alt"></i> Logout
                        </a>
                    </div>
                </div>
                
                <div class="admin-container">
                    <div class="admin-sidebar">
                        <ul class="sidebar-menu">
                            <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                            <li><a href="{{ url_for('admin_products') }}" class="active"><i class="fas fa-box-open"></i> Products</a></li>
                            <li><a href="{{ url_for('admin_orders') }}"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                            <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                            <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                        </ul>
                    </div>
                    
                    <div class="admin-content">
                        <div class="card">
                            <div class="card-header">
                                <h2>Edit Product</h2>
                                <a href="{{ url_for('admin_products') }}" class="btn">
                                    <i class="fas fa-arrow-left"></i> Back to Products
                                </a>
                            </div>
                            
                            <div class="alert alert-danger">
                                <i class="fas fa-exclamation-circle"></i> {{ error }}
                            </div>
                        </div>
                    </div>
                </div>
            </body>
            </html>
        ''', error=error)
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Edit Product - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
               :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, var(--success) 0%, #1e7e34 100%);
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .btn-success:hover {
            box-shadow: 0 6px 20px rgba(40, 167, 69, 0.4);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
        }
        
        .form-control, .form-select {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            background: rgba(255,255,255,0.8);
            transition: all 0.3s;
        }
        
        .form-control:focus, .form-select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        textarea.form-control {
            min-height: 100px;
            resize: vertical;
        }
        
        small {
            display: block;
            margin-top: 5px;
            font-size: 12px;
            color: #666;
        }
        
        .preview-image {
            max-width: 200px;
            max-height: 200px;
            margin-top: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .text-right {
            text-align: right;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}" class="active"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>Edit Product #{{ product[0] }}</h2>
                            <a href="{{ url_for('admin_products') }}" class="btn">
                                <i class="fas fa-arrow-left"></i> Back to Products
                            </a>
                        </div>
                        
                        <form method="post">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            
                            <div class="form-group">
                                <label for="title">Product Title</label>
                                <input type="text" id="title" name="title" class="form-control" value="{{ product[1] }}" required>
                            </div>
                            
                            <div class="form-group">
                                <label for="description">Description</label>
                                <textarea id="description" name="description" class="form-control" rows="4">{{ product[2] }}</textarea>
                            </div>
                            
                            <div class="form-group">
                                <label for="price">Price (₹)</label>
                                <input type="number" id="price" name="price" class="form-control" step="0.01" min="0" value="{{ product[3] }}" required>
                            </div>
                            
                            <div class="form-group">
                                <label for="image">Main Image URL</label>
                                <input type="text" id="image" name="image" class="form-control" value="{{ product[4] }}">
                                <small>Enter the filename (e.g. product1.jpg) - upload the file to static/images first</small>
                                {% if product[4] %}
                                <div>
                                    <img src="{{ url_for('static', filename='images/' + product[4]) }}" class="preview-image">
                                </div>
                                {% endif %}
                            </div>
                            
                            <div class="form-group">
                                <label for="min_quantity">Minimum Quantity</label>
                                <input type="number" id="min_quantity" name="min_quantity" class="form-control" min="1" value="{{ product[5] }}">
                            </div>
                            
                            <div class="form-group">
                                <label for="max_quantity">Maximum Quantity</label>
                                <input type="number" id="max_quantity" name="max_quantity" class="form-control" min="1" value="{{ product[6] }}">
                            </div>
                            
                            <div class="form-group">
                                <label for="discount">Discount (%)</label>
                                <input type="number" id="discount" name="discount" class="form-control" min="0" max="100" value="{{ product[7] }}">
                            </div>
                            
                            <div class="form-group">
                                <label for="rating">Rating (0-5)</label>
                                <input type="number" id="rating" name="rating" class="form-control" min="0" max="5" step="0.1" value="{{ product[8] }}">
                            </div>
                            
                            <div class="form-group">
                                <label for="stock">Stock Quantity</label>
                                <input type="number" id="stock" name="stock" class="form-control" min="0" value="{{ product[9] }}">
                            </div>
                            
                            <div class="form-group">
                                <label for="images">Additional Images (JSON array)</label>
                                <textarea id="images" name="images" class="form-control" rows="2">{{ product[10] if product[10] else '[]' }}</textarea>
                                <small>Enter as JSON array of filenames</small>
                            </div>
                            
                            <div class="form-group">
                                <label for="youtube_url">YouTube URL</label>
                                <input type="url" id="youtube_url" name="youtube_url" class="form-control" value="{{ product[11] if product[11] else '' }}" placeholder="https://youtu.be/...">
                            </div>
                            
                            <div class="form-group">
                                <label for="category">Category</label>
                                <input type="text" id="category" name="category" class="form-control" value="{{ product[12] if product[12] else '' }}">
                            </div>
                            
                            <div class="form-group">
                                <label for="tags">Tags (JSON array)</label>
                                <textarea id="tags" name="tags" class="form-control" rows="2">{{ product[13] if product[13] else '[]' }}</textarea>
                                <small>Enter as JSON array of tags</small>
                            </div>
                            
                            <div class="text-right">
                                <button type="submit" class="btn btn-success">
                                    <i class="fas fa-save"></i> Update Product
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', product=product)

@app.route('/admin/products/delete/<int:product_id>', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn.commit()
    except Exception as e:
        print(f"Error deleting product: {e}")
        flash("Error deleting product", "error")
    
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    status_filter = request.args.get('status', '')
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            query = """
                SELECT o.id, o.order_date, o.status, o.total_amount, 
                       o.advance_payment, u.name, u.phone 
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.id
            """
            params = []
            
            if status_filter:
                query += " WHERE o.status = ?"
                params.append(status_filter)
            
            query += " ORDER BY o.order_date DESC"
            c.execute(query, params)
            orders = c.fetchall()
            
    except Exception as e:
        print(f"Error fetching orders: {e}")
        orders = []
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Manage Orders - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
            margin-right: 8px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
        }
        
        .table th {
            background: rgba(248, 249, 250, 0.8);
            font-weight: 600;
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .table td {
            padding: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .table tr:hover {
            background: rgba(248, 250, 255, 0.8);
        }
        
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-processing {
            background: rgba(255, 243, 205, 0.8);
            color: #856404;
        }
        
        .status-completed {
            background: rgba(212, 237, 218, 0.8);
            color: #155724;
        }
        
        .status-shipped {
            background: rgba(204, 229, 255, 0.8);
            color: #004085;
        }
        
        .status-cancelled {
            background: rgba(248, 215, 218, 0.8);
            color: #721c24;
        }
        
        select {
            padding: 10px 15px;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            background: rgba(255,255,255,0.8);
            transition: all 0.3s;
            font-size: 14px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }
        
        select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
            
            .table {
                display: block;
                overflow-x: auto;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}" class="active"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>Manage Orders</h2>
                            <div>
                                <select id="statusFilter" onchange="filterOrders()" style="padding: 8px; border-radius: 4px;">
                                    <option value="">All Statuses</option>
                                    <option value="Processing" {% if status_filter == "Processing" %}selected{% endif %}>Processing</option>
                                    <option value="Shipped" {% if status_filter == "Shipped" %}selected{% endif %}>Shipped</option>
                                    <option value="Completed" {% if status_filter == "Completed" %}selected{% endif %}>Completed</option>
                                    <option value="Cancelled" {% if status_filter == "Cancelled" %}selected{% endif %}>Cancelled</option>
                                </select>
                            </div>
                        </div>
                        
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Order ID</th>
                                    <th>Date</th>
                                    <th>Customer</th>
                                    <th>Amount</th>
                                    <th>Advance Paid</th>
                                    <th>Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for order in orders %}
                                <tr>
                                    <td>#{{ order[0] }}</td>
                                    <td>{{ order[1] }}</td>
                                    <td>{{ order[5] or 'Guest' }} ({{ order[6] }})</td>
                                    <td>₹{{ "{:,.2f}".format(order[3]) }}</td>
                                    <td>₹{{ "{:,.2f}".format(order[4]) }}</td>
                                    <td>
                                        <span class="status-badge status-{{ order[2]|lower }}">
                                            {{ order[2] }}
                                        </span>
                                    </td>
                                    <td>
                                        <a href="{{ url_for('admin_order_detail', order_id=order[0]) }}" class="btn btn-sm">
                                            <i class="fas fa-eye"></i> View
                                        </a>
                                        <a href="{{ url_for('admin_edit_order', order_id=order[0]) }}" class="btn btn-sm">
                                            <i class="fas fa-edit"></i> Edit
                                        </a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <script>
                function filterOrders() {
                    const status = document.getElementById('statusFilter').value;
                    let url = "{{ url_for('admin_orders') }}";
                    if (status) {
                        url += "?status=" + status;
                    }
                    window.location.href = url;
                }
            </script>
        </body>
        </html>
    ''', orders=orders, status_filter=status_filter)

@app.route('/admin/orders/<int:order_id>')
@admin_required
def admin_order_detail(order_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            c.execute("""
                SELECT o.*, u.name, u.email, u.phone, u.address, u.state, u.city
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.id
                WHERE o.id = ?
            """, (order_id,))
            order = c.fetchone()
            
            if not order:
                return "Order not found", 404
                
    except Exception as e:
        print(f"Error fetching order: {e}")
        return "Error fetching order details", 500
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Order Details - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
            margin-right: 8px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-processing {
            background: rgba(255, 243, 205, 0.8);
            color: #856404;
        }
        
        .status-completed {
            background: rgba(212, 237, 218, 0.8);
            color: #155724;
        }
        
        .status-shipped {
            background: rgba(204, 229, 255, 0.8);
            color: #004085;
        }
        
        .status-cancelled {
            background: rgba(248, 215, 218, 0.8);
            color: #721c24;
        }
        
        .order-details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }
        
        .order-section {
            margin-bottom: 25px;
            background: rgba(248, 249, 250, 0.5);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.03);
        }
        
        .order-section h3 {
            margin-top: 0;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
            color: var(--primary-dark);
            font-size: 18px;
        }
        
        .detail-row {
            display: flex;
            margin-bottom: 12px;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(0,0,0,0.03);
        }
        
        .detail-label {
            font-weight: 600;
            width: 150px;
            color: #555;
        }
        
        .items-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .items-list li {
            padding: 12px 0;
            border-bottom: 1px solid rgba(0,0,0,0.05);
            display: flex;
            justify-content: space-between;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
            
            .order-details {
                grid-template-columns: 1fr;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
            
            .card-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 15px;
            }
            
            .detail-row {
                flex-direction: column;
                gap: 5px;
            }
            
            .detail-label {
                width: 100%;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}" class="active"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>Order Details #{{ order[0] }}</h2>
                            <div>
                                <a href="{{ url_for('admin_orders') }}" class="btn">
                                    <i class="fas fa-arrow-left"></i> Back to Orders
                                </a>
                                <a href="{{ url_for('admin_edit_order', order_id=order[0]) }}" class="btn">
                                    <i class="fas fa-edit"></i> Edit Order
                                </a>
                            </div>
                        </div>
                        
                        <div class="order-details">
                            <div>
                                <div class="order-section">
                                    <h3>Order Information</h3>
                                    <div class="detail-row">
                                        <span class="detail-label">Order Date:</span>
                                        <span>{{ order[1] }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Order Status:</span>
                                        <span class="status-badge status-{{ order[14]|lower }}">
                                            {{ order[14] }}
                                        </span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Transaction ID:</span>
                                        <span>{{ order[7] }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Can Cancel:</span>
                                        <span>{{ "Yes" if order[15] else "No" }}</span>
                                    </div>
                                </div>
                                
                                <div class="order-section">
                                    <h3>Customer Information</h3>
                                    <div class="detail-row">
                                        <span class="detail-label">Name:</span>
                                        <span>{{ order[2] }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Phone:</span>
                                        <span>{{ order[3] }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Email:</span>
                                        <span>{{ order[17] or 'Not provided' }}</span>
                                    </div>
                                </div>
                                
                                <div class="order-section">
                                    <h3>Shipping Information</h3>
                                    <div class="detail-row">
                                        <span class="detail-label">Address:</span>
                                        <span>{{ order[6] }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">City:</span>
                                        <span>{{ order[5] }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">State:</span>
                                        <span>{{ order[4] }}</span>
                                    </div>
                                </div>
                            </div>
                            
                            <div>
                                <div class="order-section">
                                    <h3>Order Summary</h3>
                                    <div class="detail-row">
                                        <span class="detail-label">Subtotal:</span>
                                        <span>₹{{ "{:,.2f}".format(order[8]) }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Delivery Charge:</span>
                                        <span>₹{{ "{:,.2f}".format(order[9]) }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Total Amount:</span>
                                        <span>₹{{ "{:,.2f}".format(order[10]) }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Advance Paid:</span>
                                        <span>₹{{ "{:,.2f}".format(order[11]) }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Balance Due:</span>
                                        <span>₹{{ "{:,.2f}".format(order[10] - order[11]) }}</span>
                                    </div>
                                </div>
                                
                                <div class="order-section">
                                    <h3>Order Items</h3>
                                    <ul class="items-list">
                                        {% for item in order[12].split(', ') %}
                                        <li>{{ item }}</li>
                                        {% endfor %}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', order=order)

@app.route('/admin/orders/edit/<int:order_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_order(order_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            if request.method == 'POST':
                status = request.form['status']
                can_cancel = 1 if request.form.get('can_cancel') else 0
                
                c.execute("""
                    UPDATE orders SET 
                    status = ?, can_cancel = ?
                    WHERE id = ?
                """, (status, can_cancel, order_id))
                conn.commit()
                
                return redirect(url_for('admin_order_detail', order_id=order_id))
            
            c.execute("""
                SELECT o.*, u.name, u.email, u.phone, u.address, u.state, u.city
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.id
                WHERE o.id = ?
            """, (order_id,))
            order = c.fetchone()
            
            if not order:
                return "Order not found", 404
                
    except Exception as e:
        print(f"Error editing order: {e}")
        return "Error editing order", 500
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Edit Order - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, var(--success) 0%, #1e7e34 100%);
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .btn-success:hover {
            box-shadow: 0 6px 20px rgba(40, 167, 69, 0.4);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
        }
        
        .form-control, .form-select {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            background: rgba(255,255,255,0.8);
            transition: all 0.3s;
        }
        
        .form-control:focus, .form-select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        input[type="checkbox"] {
            width: 18px;
            height: 18px;
            margin-right: 10px;
            accent-color: var(--primary);
        }
        
        .form-group label {
            display: flex;
            align-items: center;
            cursor: pointer;
        }
        
        .text-right {
            text-align: right;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
            
            .card-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 15px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}" class="active"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>Edit Order #{{ order[0] }}</h2>
                            <div>
                                <a href="{{ url_for('admin_order_detail', order_id=order[0]) }}" class="btn">
                                    <i class="fas fa-arrow-left"></i> Back to Order
                                </a>
                            </div>
                        </div>
                        
                        <form method="post">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            
                            <div class="form-group">
                                <label for="status">Order Status</label>
                                <select id="status" name="status" class="form-select">
                                    <option value="Processing" {% if order[14] == "Processing" %}selected{% endif %}>Processing</option>
                                    <option value="Shipped" {% if order[14] == "Shipped" %}selected{% endif %}>Shipped</option>
                                    <option value="Completed" {% if order[14] == "Completed" %}selected{% endif %}>Completed</option>
                                    <option value="Cancelled" {% if order[14] == "Cancelled" %}selected{% endif %}>Cancelled</option>
                                </select>
                            </div>
                            
                            <div class="form-group">
                                <label>
                                    <input type="checkbox" name="can_cancel" {% if order[15] %}checked{% endif %}>
                                    Allow customer to cancel this order
                                </label>
                            </div>
                            
                            <div class="text-right">
                                <button type="submit" class="btn btn-success">
                                    <i class="fas fa-save"></i> Update Order
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', order=order)

@app.route('/admin/users')
@admin_required
def admin_users():
    search_query = request.args.get('search', '')
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            if search_query:
                c.execute("""
                    SELECT * FROM users 
                    WHERE phone LIKE ? OR name LIKE ? OR email LIKE ?
                    ORDER BY created_at DESC
                """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
            else:
                c.execute("SELECT * FROM users ORDER BY created_at DESC")
            
            users = c.fetchall()
            
    except Exception as e:
        print(f"Error fetching users: {e}")
        users = []
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Manage Users - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
               :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
            flex-wrap: wrap;
            gap: 15px;
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
        }
        
        .table th {
            background: rgba(248, 249, 250, 0.8);
            font-weight: 600;
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .table td {
            padding: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .table tr:hover {
            background: rgba(248, 250, 255, 0.8);
        }
        
        .search-form {
            display: flex;
            gap: 10px;
            flex: 1;
            min-width: 300px;
            max-width: 600px;
        }
        
        .search-form input[type="text"] {
            flex: 1;
            padding: 10px 15px;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            background: rgba(255,255,255,0.8);
            transition: all 0.3s;
        }
        
        .search-form input[type="text"]:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
            
            .table {
                display: block;
                overflow-x: auto;
            }
            
            .card-header {
                flex-direction: column;
                align-items: stretch;
            }
            
            .search-form {
                width: 100%;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}" class="active"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>Manage Users</h2>
                            <form method="get" style="display: flex; gap: 10px;">
                                <input type="text" name="search" placeholder="Search users..." value="{{ search_query }}" style="flex: 1;">
                                <button type="submit" class="btn">
                                    <i class="fas fa-search"></i> Search
                                </button>
                                <a href="{{ url_for('admin_users') }}" class="btn btn-danger">
                                    <i class="fas fa-times"></i> Clear
                                </a>
                            </form>
                        </div>
                        
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Phone</th>
                                    <th>Name</th>
                                    <th>Email</th>
                                    <th>Address</th>
                                    <th>Joined</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for user in users %}
                                <tr>
                                    <td>#{{ user[0] }}</td>
                                    <td>{{ user[1] }}</td>
                                    <td>{{ user[2] or '-' }}</td>
                                    <td>{{ user[3] or '-' }}</td>
                                    <td>
                                        {% if user[4] %}
                                            {{ user[4] }}, {{ user[6] }}, {{ user[5] }}
                                        {% else %}
                                            -
                                        {% endif %}
                                    </td>
                                    <td>{{ user[7] }}</td>
                                    <td>
                                        <a href="{{ url_for('admin_user_detail', user_id=user[0]) }}" class="btn btn-sm">
                                            <i class="fas fa-eye"></i> View
                                        </a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', users=users, search_query=search_query)

@app.route('/admin/users/<int:user_id>')
@admin_required
def admin_user_detail(user_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            # Get user details
            c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user = c.fetchone()
            
            if not user:
                return "User not found", 404
            
            # Get user's orders
            c.execute("""
                SELECT id, order_date, status, total_amount 
                FROM orders 
                WHERE user_id = ?
                ORDER BY order_date DESC
            """, (user_id,))
            orders = c.fetchall()
            
    except Exception as e:
        print(f"Error fetching user details: {e}")
        return "Error fetching user details", 500
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>User Details - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .user-details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }
        
        .user-section {
            margin-bottom: 25px;
            background: rgba(248, 249, 250, 0.5);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.03);
        }
        
        .user-section h3 {
            margin-top: 0;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
            color: var(--primary-dark);
            font-size: 18px;
        }
        
        .detail-row {
            display: flex;
            margin-bottom: 12px;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(0,0,0,0.03);
        }
        
        .detail-label {
            font-weight: 600;
            width: 150px;
            color: #555;
        }
        
        .orders-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
        }
        
        .orders-table th {
            background: rgba(248, 249, 250, 0.8);
            font-weight: 600;
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .orders-table td {
            padding: 12px 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .orders-table tr:hover {
            background: rgba(248, 250, 255, 0.8);
        }
        
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-processing {
            background: rgba(255, 243, 205, 0.8);
            color: #856404;
        }
        
        .status-completed {
            background: rgba(212, 237, 218, 0.8);
            color: #155724;
        }
        
        .status-shipped {
            background: rgba(204, 229, 255, 0.8);
            color: #004085;
        }
        
        .status-cancelled {
            background: rgba(248, 215, 218, 0.8);
            color: #721c24;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
            
            .user-details {
                grid-template-columns: 1fr;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
            
            .card-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 15px;
            }
            
            .detail-row {
                flex-direction: column;
                gap: 5px;
            }
            
            .detail-label {
                width: 100%;
            }
            
            .orders-table {
                display: block;
                overflow-x: auto;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}" class="active"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>User Details #{{ user[0] }}</h2>
                            <div>
                                <a href="{{ url_for('admin_users') }}" class="btn">
                                    <i class="fas fa-arrow-left"></i> Back to Users
                                </a>
                            </div>
                        </div>
                        
                        <div class="user-details">
                            <div>
                                <div class="user-section">
                                    <h3>Basic Information</h3>
                                    <div class="detail-row">
                                        <span class="detail-label">Phone:</span>
                                        <span>{{ user[1] }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Name:</span>
                                        <span>{{ user[2] or '-' }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Email:</span>
                                        <span>{{ user[3] or '-' }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Joined:</span>
                                        <span>{{ user[7] }}</span>
                                    </div>
                                </div>
                                
                                <div class="user-section">
                                    <h3>Address Information</h3>
                                    <div class="detail-row">
                                        <span class="detail-label">Address:</span>
                                        <span>{{ user[4] or '-' }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">City:</span>
                                        <span>{{ user[6] or '-' }}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">State:</span>
                                        <span>{{ user[5] or '-' }}</span>
                                    </div>
                                </div>
                            </div>
                            
                            <div>
                                <div class="user-section">
                                    <h3>Order History</h3>
                                    {% if orders %}
                                    <table class="orders-table">
                                        <thead>
                                            <tr>
                                                <th>Order ID</th>
                                                <th>Date</th>
                                                <th>Status</th>
                                                <th>Amount</th>
                                                <th>Action</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {% for order in orders %}
                                            <tr>
                                                <td>#{{ order[0] }}</td>
                                                <td>{{ order[1] }}</td>
                                                <td>
                                                    <span class="status-badge status-{{ order[2]|lower }}">
                                                        {{ order[2] }}
                                                    </span>
                                                </td>
                                                <td>₹{{ "{:,.2f}".format(order[3]) }}</td>
                                                <td>
                                                    <a href="{{ url_for('admin_order_detail', order_id=order[0]) }}" class="btn btn-sm">
                                                        <i class="fas fa-eye"></i> View
                                                    </a>
                                                </td>
                                            </tr>
                                            {% endfor %}
                                        </tbody>
                                    </table>
                                    {% else %}
                                    <p>No orders found for this user.</p>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', user=user, orders=orders)


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        try:
            # Update delivery charges
            new_charges = {}
            states = request.form.getlist('state[]')
            cities = request.form.getlist('city[]')
            charges = request.form.getlist('charge[]')
            
            for i in range(len(states)):
                state = states[i]
                city = cities[i]
                charge = int(charges[i]) if charges[i] else 0
                
                if state not in new_charges:
                    new_charges[state] = {}
                new_charges[state][city] = charge
            
            # In a real application, you would save this to a database or config file
            # For this example, we'll just update the global variable
            global DELIVERY_CHARGES
            DELIVERY_CHARGES = new_charges
            
            return redirect(url_for('admin_settings'))
        
        except Exception as e:
            print(f"Error updating settings: {e}")
            error = "Error updating settings"
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Settings - CRONYZO Admin</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
            --primary: #4361ee;
            --primary-dark: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ffc107;
            --info: #17a2b8;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
            color: var(--dark);
        }
        
        .admin-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .admin-container {
            display: flex;
            min-height: calc(100vh - 65px);
        }
        
        .admin-sidebar {
            width: 280px;
            background: rgba(255,255,255,0.95);
            box-shadow: 2px 0 15px rgba(0,0,0,0.05);
            padding: 25px 0;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            padding: 14px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            font-weight: 500;
            margin: 5px 15px;
            border-radius: 8px;
        }
        
        .sidebar-menu li a:hover {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            transform: translateX(5px);
        }
        
        .sidebar-menu li a.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
        }
        
        .sidebar-menu li a i {
            margin-right: 12px;
            width: 20px;
            text-align: center;
            font-size: 18px;
        }
        
        .admin-content {
            flex: 1;
            padding: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .card-header h2 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--primary-dark);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
            border: none;
            cursor: pointer;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }
        
        .btn-sm {
            padding: 8px 15px;
            font-size: 13px;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #c82333 100%);
            box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
        }
        
        .btn-danger:hover {
            box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, var(--success) 0%, #1e7e34 100%);
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .btn-success:hover {
            box-shadow: 0 6px 20px rgba(40, 167, 69, 0.4);
        }
        
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 25px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .alert-danger {
            background: rgba(248, 215, 218, 0.8);
            color: #721c24;
        }
        
        .delivery-charge-form {
            margin-bottom: 30px;
        }
        
        .delivery-charge-row {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
            align-items: center;
        }
        
        .delivery-charge-row input,
        .delivery-charge-row select {
            padding: 12px 15px;
            border: 1px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            background: rgba(255,255,255,0.8);
            flex: 1;
            min-width: 150px;
        }
        
        .delivery-charge-row input:focus,
        .delivery-charge-row select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        #deliveryChargesContainer {
            margin-top: 20px;
        }
        
        h3 {
            color: var(--primary-dark);
            margin-top: 25px;
            margin-bottom: 15px;
            font-size: 18px;
        }
        
        .text-right {
            text-align: right;
        }
        
        @media (max-width: 992px) {
            .admin-sidebar {
                width: 220px;
            }
        }
        
        @media (max-width: 768px) {
            .admin-container {
                flex-direction: column;
            }
            
            .admin-sidebar {
                width: 100%;
                padding: 15px 0;
            }
            
            .sidebar-menu {
                display: flex;
                overflow-x: auto;
                padding: 0 15px;
            }
            
            .sidebar-menu li {
                flex: 0 0 auto;
            }
            
            .sidebar-menu li a {
                margin: 0 5px;
                padding: 10px 15px;
            }
            
            .delivery-charge-row {
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }
        }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="admin-header">
                <h1>CRONYZO Admin</h1>
                <div>
                    <a href="{{ url_for('admin_logout') }}" class="btn btn-danger">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </a>
                </div>
            </div>
            
            <div class="admin-container">
                <div class="admin-sidebar">
                    <ul class="sidebar-menu">
                        <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                        <li><a href="{{ url_for('admin_products') }}"><i class="fas fa-box-open"></i> Products</a></li>
                        <li><a href="{{ url_for('admin_orders') }}"><i class="fas fa-shopping-bag"></i> Orders</a></li>
                        <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Users</a></li>
                        <li><a href="{{ url_for('admin_settings') }}" class="active"><i class="fas fa-cog"></i> Settings</a></li>
                    </ul>
                </div>
                
                <div class="admin-content">
                    <div class="card">
                        <div class="card-header">
                            <h2>System Settings</h2>
                        </div>
                        
                        {% if error %}
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-circle"></i> {{ error }}
                        </div>
                        {% endif %}
                        
                        <form method="post">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            
                            <h3>Delivery Charges</h3>
                            <div id="deliveryChargesContainer">
                                {% for state, cities in delivery_charges.items() %}
                                    {% for city, charge in cities.items() %}
                                    <div class="delivery-charge-row">
                                        <input type="text" name="state[]" placeholder="State" value="{{ state }}" required>
                                        <input type="text" name="city[]" placeholder="City" value="{{ city }}" required>
                                        <input type="number" name="charge[]" placeholder="Charge" value="{{ charge }}" min="0" required>
                                        <button type="button" class="btn btn-danger" onclick="removeDeliveryCharge(this)">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                    {% endfor %}
                                {% endfor %}
                            </div>
                            
                            <button type="button" class="btn" onclick="addDeliveryCharge()" style="margin-top: 10px;">
                                <i class="fas fa-plus"></i> Add Delivery Charge
                            </button>
                            
                            <div class="text-right" style="margin-top: 30px;">
                                <button type="submit" class="btn btn-success">
                                    <i class="fas fa-save"></i> Save Settings
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
            <!-- For the upload page -->
<a href="/upload_image">
  <button>Upload Image</button>
</a>

<!-- For the image list page -->
<a href="/list_images">
  <button>View All Images</button>
</a>

<!-- For the admin management page -->
<a href="/admin/images">
  <button>Image Manager (Admin)</button>
</a>
            <script>
                function addDeliveryCharge() {
                    const container = document.getElementById('deliveryChargesContainer');
                    const newRow = document.createElement('div');
                    newRow.className = 'delivery-charge-row';
                    newRow.innerHTML = `
                        <input type="text" name="state[]" placeholder="State" required>
                        <input type="text" name="city[]" placeholder="City" required>
                        <input type="number" name="charge[]" placeholder="Charge" min="0" required>
                        <button type="button" class="btn btn-danger" onclick="removeDeliveryCharge(this)">
                            <i class="fas fa-trash"></i>
                        </button>
                    `;
                    container.appendChild(newRow);
                }
                
                function removeDeliveryCharge(button) {
                    const row = button.parentElement;
                    row.remove();
                }
            </script>
        </body>
        </html>
    ''', delivery_charges=DELIVERY_CHARGES, error=error if 'error' in locals() else None)
    
import os
from werkzeug.utils import secure_filename

# Configure upload settings
app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/upload_image', methods=['POST'])
def upload_image():
    try:
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add random string to filename to prevent overwrites
        unique_filename = f"{secrets.token_hex(8)}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        try:
            file.save(filepath)
            return jsonify({
                'success': True,
                'filename': unique_filename,
                'url': url_for('static', filename=f'images/{unique_filename}')
            }), 200
        except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/delete_image', methods=['POST'])
def delete_image():
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({'error': 'No filename provided'}), 400
    
    filename = data['filename']
    if not filename or not isinstance(filename, str):
        return jsonify({'error': 'Invalid filename'}), 400
    
    # Prevent directory traversal
    if '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    try:
        os.remove(filepath)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/list_images')
def list_images():
    try:
        images = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename):
                images.append({
                    'name': filename,
                    'url': url_for('static', filename=f'images/{filename}')
                })
        return jsonify({'images': images}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin routes for image management
@app.route('/admin/images')
@csrf.exempt  # You might want to add proper admin authentication
def admin_images():
    try:
        images = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename):
                images.append({
                    'name': filename,
                    'url': url_for('static', filename=f'images/{filename}'),
                    'size': os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                })
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Image Manager</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    .image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
                    .image-card { border: 1px solid #ddd; padding: 10px; border-radius: 5px; }
                    .image-card img { max-width: 100%; height: auto; }
                    .actions { margin-top: 10px; display: flex; justify-content: space-between; }
                    .upload-form { margin: 20px 0; padding: 20px; background: #f5f5f5; border-radius: 5px; }
                </style>
            </head>
            <body>
                <h1>Image Manager</h1>
                
                <div class="upload-form">
                    <h2>Upload New Image</h2>
                    <form id="uploadForm" enctype="multipart/form-data">
                        <input type="file" name="file" id="fileInput" required>
                        <button type="submit">Upload</button>
                    </form>
                    <div id="uploadStatus"></div>
                </div>
                
                <h2>Existing Images</h2>
                <div class="image-grid" id="imageGrid">
                    {% for image in images %}
                    <div class="image-card">
                        <img src="{{ image.url }}" alt="{{ image.name }}">
                        <div>{{ image.name }}</div>
                        <div>{{ (image.size / 1024)|round(2) }} KB</div>
                        <div class="actions">
                            <button onclick="copyUrl('{{ image.url }}')">Copy URL</button>
                            <button onclick="deleteImage('{{ image.name }}')" style="color: red;">Delete</button>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                
                <script>
                    document.getElementById('uploadForm').addEventListener('submit', async function(e) {
                        e.preventDefault();
                        const fileInput = document.getElementById('fileInput');
                        const formData = new FormData();
                        formData.append('file', fileInput.files[0]);
                        
                        const statusDiv = document.getElementById('uploadStatus');
                        statusDiv.textContent = 'Uploading...';
                        statusDiv.style.color = 'blue';
                        
                        
                            
                            try {
    const response = await fetch('/upload_image', {
        method: 'POST',
        body: formData
    });
    
    // First check if response is JSON
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        throw new Error(text || 'Invalid response from server');
    }
    
    const data = await response.json();
                            
                            if (data.success) {
                                statusDiv.textContent = 'Upload successful!';
                                statusDiv.style.color = 'green';
                                // Reload the page to show the new image
                                setTimeout(() => location.reload(), 1000);
                            } else {
                                statusDiv.textContent = 'Error: ' + (data.error || 'Upload failed');
                                statusDiv.style.color = 'red';
                            }

                        } catch (error) {
    statusDiv.textContent = 'Error: ' + error.message;
    statusDiv.style.color = 'red';
}
                    });
                    
                    function copyUrl(url) {
                        navigator.clipboard.writeText(url)
                            .then(() => alert('URL copied to clipboard'))
                            .catch(err => alert('Failed to copy URL: ' + err));
                    }
                    
                    async function deleteImage(filename) {
                        if (!confirm('Are you sure you want to delete this image?')) return;
                        
                        try {
                            const response = await fetch('/delete_image', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({ filename: filename })
                            });
                            
                            const data = await response.json();
                            
                            if (data.success) {
                                alert('Image deleted successfully');
                                location.reload();
                            } else {
                                alert('Error: ' + (data.error || 'Delete failed'));
                            }
                        } catch (error) {
                            alert('Error: ' + error.message);
                        }
                    }
                </script>
            </body>
            </html>
        ''', images=images)
    except Exception as e:
        return f"Error: {str(e)}", 500
# ==================== END ADMIN PANEL ====================
if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    if not os.path.exists('static/images'):
        os.makedirs('static/images')
    app.run(debug=True)
    app.config['WTF_CSRF_ENABLED'] = False
