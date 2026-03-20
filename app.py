"""
Conect Us - Home Services Platform
Main Flask Application with MongoDB Integration
"""

from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import random
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from pymongo import MongoClient
from bson.objectid import ObjectId
import certifi
from authlib.integrations.flask_client import OAuth
import requests

# Initialize Flask app
app = Flask(__name__)
SECRET_KEY = os.environ.get('SECRET_KEY', 'conect-us-secret-key-change-in-production')
app.config['SECRET_KEY'] = SECRET_KEY

# Setup MongoDB Connection
MONGO_URI = os.environ.get('MONGO_URI')
if not MONGO_URI:
    # Fallback to local for dev if no env var
    MONGO_URI = 'mongodb://localhost:27017/'
    print("WARNING: MONGO_URI environment variable not set. Falling back to localhost.")

try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    db = client['conect_us']
except Exception as e:
    print(f"FAILED to initialize MongoDB client: {e}")
    db = None # Routes will fail gracefully if they check for db

# Fixed admin credentials
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@conectus.com')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@123')

# Initialize extensions
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Flask-Mail for sending OTP emails using provided credentials
try:
    from flask_mail import Mail, Message
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'shahkushal0306@gmail.com')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'ragt umlq ermt dbtm')
    app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']
    mail = Mail(app)
    FLASK_MAIL_AVAILABLE = True
    print(f"Flask-Mail configured successfully.")
except ImportError:
    mail = None
    FLASK_MAIL_AVAILABLE = False
    print("Flask-Mail not installed. Email OTP will not work.")

# OAuth Setup
oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url=os.environ.get('GOOGLE_DISCOVERY_URL'),
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# User Document Wrapper
class User(UserMixin):
    def __init__(self, data):
        self.id = str(data.get('_id'))
        self.name = data.get('name')
        self.email = data.get('email')
        self.phone = data.get('phone')
        self.password_hash = data.get('password_hash')
        self.is_admin = data.get('is_admin', False)

@login_manager.user_loader
def load_user(user_id):
    try:
        u = db.users.find_one({"_id": ObjectId(user_id)})
        return User(u) if u else None
    except:
        return None


# Helper function to prep dicts for templates
def to_dict_with_id(doc):
    if not doc:
        return None
    # Provide .id attribute to dictionary to match SQLAlchemy model behavior if jinja accesses {{ service.id }}
    doc['id'] = str(doc['_id'])
    return doc


# Routes

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/home')
def home():
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    home_services = [to_dict_with_id(d) for d in db.service_categories.find({'category_type': 'home'})]
    commercial_services = [to_dict_with_id(d) for d in db.service_categories.find({'category_type': 'commercial'})]
    return render_template('dashboard.html', 
                           home_services=home_services, 
                           commercial_services=commercial_services)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        
        user_data = db.users.find_one({'email': email})
        
        if user_data and check_password_hash(user_data.get('password_hash', ''), password):
            user = User(user_data)
            login_user(user)
            if user.is_admin and email == ADMIN_EMAIL:
                return redirect(url_for('admin_dashboard'))
            if user.is_admin and email != ADMIN_EMAIL:
                logout_user()
                flash('Admin access is restricted.', 'error')
                return render_template('login.html')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('signup.html')


@app.route('/send_otp', methods=['POST'])
def send_otp():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone')
        password = request.form.get('password')

        if email == ADMIN_EMAIL:
            return jsonify({'success': False, 'message': 'This email is reserved and cannot be used for signup'})
        
        if db.users.find_one({'email': email}):
            return jsonify({'success': False, 'message': 'Email already registered'})
        
        # Remove any pending OTPs for this email to avoid duplicates
        db.otp_verifications.delete_many({'email': email})
        
        otp_code = str(random.randint(100000, 999999))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        hashed_password = generate_password_hash(password)
        
        db.otp_verifications.insert_one({
            'email': email,
            'otp_code': otp_code,
            'name': name,
            'phone': phone,
            'password_hash': hashed_password,
            'is_admin': False,
            'created_at': datetime.now(timezone.utc),
            'expires_at': expires_at,
            'is_verified': False
        })
        
        if FLASK_MAIL_AVAILABLE:
            try:
                msg = Message(
                    subject='Your Conect Us Verification Code',
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[email]
                )
                msg.body = f"Hello {name},\n\nYour verification code is: {otp_code}\n\nThis code will expire in 5 minutes.\n\nBest regards,\nConect Us Team"
                mail.send(msg)
            except Exception as e:
                print(f"Email sending failed: {e}")
                # Optional: Handle error without interrupting flow, just log it.
        
        return jsonify({
            'success': True, 
            'message': 'OTP sent successfully!',
            'email': email,
            'otp': otp_code  # Removing in production could be safer, but helps development/fallback
        })
    return jsonify({'success': False, 'message': 'Invalid request'})


@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    if request.method == 'POST':
        email = request.form.get('email')
        otp = request.form.get('otp')
        
        otp_record = db.otp_verifications.find_one({
            'email': email, 
            'otp_code': otp, 
            'is_verified': False
        })
        
        if not otp_record:
            return jsonify({'success': False, 'message': 'Invalid OTP'})
        
        if otp_record.get('expires_at') and otp_record['expires_at'].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            db.otp_verifications.delete_one({'_id': otp_record['_id']})
            return jsonify({'success': False, 'message': 'OTP has expired. Please request a new one.'})
        
        # Mark as verified
        db.otp_verifications.update_one({'_id': otp_record['_id']}, {'$set': {'is_verified': True}})
        
        # Create user account
        db.users.insert_one({
            'name': otp_record.get('name'),
            'email': otp_record.get('email'),
            'phone': otp_record.get('phone'),
            'password_hash': otp_record.get('password_hash'),
            'is_admin': otp_record.get('is_admin', False)
        })
        
        db.otp_verifications.delete_one({'_id': otp_record['_id']})
        
        return jsonify({'success': True, 'message': 'Account created successfully!'})
    return jsonify({'success': False, 'message': 'Invalid request'})


@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    if request.method == 'POST':
        email = request.form.get('email')
        otp_record = db.otp_verifications.find_one({'email': email, 'is_verified': False})
        
        if not otp_record:
            return jsonify({'success': False, 'message': 'No pending registration found. Please register again.'})
        
        otp_code = str(random.randint(100000, 999999))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        db.otp_verifications.update_one(
            {'_id': otp_record['_id']},
            {'$set': {'otp_code': otp_code, 'expires_at': expires_at}}
        )

        name = otp_record.get('name', 'User')

        if FLASK_MAIL_AVAILABLE:
            try:
                msg = Message(
                    subject='Your Conect Us Verification Code (Resent)',
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[email]
                )
                msg.body = f"Hello {name},\n\nYour new verification code is: {otp_code}\n\nThis code will expire in 5 minutes.\n\nBest regards,\nConect Us Team"
                mail.send(msg)
            except Exception as e:
                print(f"Email sending failed: {e}")
        
        return jsonify({
            'success': True, 
            'message': 'New OTP sent successfully!',
            'otp': otp_code # Returning for convenience, remove for deep security
        })
    return jsonify({'success': False, 'message': 'Invalid request'})


@app.route('/google_login')
def google_login():
    # Attempt to use the REDIRECT_URI from .env if available, otherwise fallback to url_for
    # Note: Google Console must have this exact URI registered.
    redirect_uri = os.environ.get('REDIRECT_URI')
    if not redirect_uri:
        redirect_uri = url_for('google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/login/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')
        if user_info:
            email = user_info['email'].lower()
            user_data = db.users.find_one({'email': email})
            if not user_data:
                # Create new user if not exists
                db.users.insert_one({
                    'name': user_info.get('name', email.split('@')[0]),
                    'email': email,
                    'phone': '',
                    'password_hash': None, # No password for Google users
                    'is_admin': False
                })
                user_data = db.users.find_one({'email': email})
            
            user = User(user_data)
            login_user(user)
            flash(f'Logged in successfully as {user.name}', 'success')
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Auth Error: {e}")
        flash('Login failed. Please try again.', 'error')
        
    return redirect(url_for('login'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/service/<service_id>')
@login_required
def service_detail(service_id):
    try:
        sid = ObjectId(service_id)
    except:
        sid = service_id
    service = db.service_categories.find_one({'_id': sid})
    if service:
        service = to_dict_with_id(service)
    
    sub_services = [to_dict_with_id(d) for d in db.service_sub_categories.find({'category_id': service_id})]
    return render_template('service_detail.html', service=service, sub_services=sub_services)


@app.route('/book_service', methods=['POST'])
@login_required
def book_service():
    service_id = request.form.get('service_id')
    service_name = request.form.get('service_name')
    address = request.form.get('address')
    description = request.form.get('description')
    phone = request.form.get('phone')
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    
    db.booking_requests.insert_one({
        'user_id': str(current_user.id),
        'service_id': str(service_id),
        'service_name': service_name,
        'user_name': current_user.name,
        'user_email': current_user.email,
        'user_phone': phone,
        'address': address,
        'description': description,
        'latitude': float(latitude) if latitude else None,
        'longitude': float(longitude) if longitude else None,
        'status': 'pending',
        'created_at': datetime.now(timezone.utc)
    })
    
    flash('Service booked successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/my_bookings')
@login_required
def my_bookings():
    bookings = [to_dict_with_id(d) for d in db.booking_requests.find({'user_id': str(current_user.id)}).sort('created_at', -1)]
    return render_template('my_bookings.html', bookings=bookings)


# Admin Routes

@app.route('/admin')
def admin():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/admin_login.html')

@app.route('/admin_login', methods=['POST'])
def admin_login_post():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password')

    if email != ADMIN_EMAIL:
        flash('Invalid admin credentials', 'error')
        return redirect(url_for('admin'))

    user_data = db.users.find_one({'email': ADMIN_EMAIL, 'is_admin': True})
    
    # Auto setup admin if not present
    if not user_data:
        db.users.insert_one({
            'name': 'Admin',
            'email': ADMIN_EMAIL,
            'password_hash': generate_password_hash(ADMIN_PASSWORD),
            'is_admin': True
        })
        user_data = db.users.find_one({'email': ADMIN_EMAIL, 'is_admin': True})

    if user_data and check_password_hash(user_data.get('password_hash'), password):
        user = User(user_data)
        login_user(user)
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Invalid admin credentials', 'error')
        return redirect(url_for('admin'))

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    all_bookings = [to_dict_with_id(b) for b in db.booking_requests.find().sort('created_at', -1)]
    return render_template('admin/admin_dashboard.html', bookings=all_bookings)

@app.route('/admin/client_activities')
@login_required
def client_activities():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    clients = [to_dict_with_id(c) for c in db.users.find({'is_admin': False})]
    all_bookings = [to_dict_with_id(b) for b in db.booking_requests.find().sort('created_at', -1)]
    
    total_clients = len(clients)
    total_bookings = len(all_bookings)
    pending_bookings = db.booking_requests.count_documents({'status': 'pending'})
    completed_bookings = db.booking_requests.count_documents({'status': 'completed'})
    
    return render_template('admin/client_activities.html', 
                         clients=clients, 
                         bookings=all_bookings,
                         total_clients=total_clients,
                         total_bookings=total_bookings,
                         pending_bookings=pending_bookings,
                         completed_bookings=completed_bookings)

@app.route('/admin/update_booking/<booking_id>/<action>')
@login_required
def update_booking(booking_id, action):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        bid = ObjectId(booking_id)
    except:
        bid = booking_id
        
    status_map = {
        'accept': 'accepted',
        'complete': 'completed',
        'cancel': 'cancelled'
    }
    
    if action in status_map:
        db.booking_requests.update_one({'_id': bid}, {'$set': {'status': status_map[action]}})
        flash(f'Booking {status_map[action]} successfully!', 'success')
    
    return redirect(url_for('admin_dashboard'))

def init_db():
    if db is None:
        print("Skipping DB initialization: db is None")
        return
    # Only populate if empty
    try:
        if db.service_categories.count_documents({}) == 0:
            home_services = [
                {'name': 'Plumber', 'description': 'Fix leaks, pipe fitting, and plumbing issues', 
                 'image_url': 'https://cdn.pixabay.com/photo/2017/09/26/11/10/plumber-2788332_1280.jpg', 'category_type': 'home'},
                {'name': 'Electrician', 'description': 'Electrical repairs and installations',
                 'image_url': 'https://cdn.pixabay.com/photo/2015/05/01/18/13/electrician-748832_1280.jpg', 'category_type': 'home'},
                {'name': 'Carpenter', 'description': 'Furniture repair and custom carpentry',
                 'image_url': 'https://cdn.pixabay.com/photo/2022/04/14/05/54/carpenter-7131654_1280.jpg', 'category_type': 'home'},
                {'name': 'House Cleaning', 'description': 'Deep cleaning and regular housekeeping',
                 'image_url': 'https://cdn.pixabay.com/photo/2019/04/02/18/16/cleaning-4098410_1280.jpg', 'category_type': 'home'},
                {'name': 'AC Repair', 'description': 'Air conditioner service and repair',
                 'image_url': 'https://cdn.pixabay.com/photo/2021/12/14/07/34/worker-6869868_1280.jpg', 'category_type': 'home'},
                {'name': 'Pest Control', 'description': 'Pest extermination services',
                 'image_url': 'https://cdn.pixabay.com/photo/2020/04/26/04/38/disinfectant-5093503_1280.jpg', 'category_type': 'home'},
                {'name': 'Painting', 'description': 'Interior and exterior wall painting',
                 'image_url': 'https://cdn.pixabay.com/photo/2017/09/15/10/24/painter-2751662_1280.jpg', 'category_type': 'home'},
                {'name': 'Appliance Repair', 'description': 'Repair service for home appliances',
                 'image_url': 'https://cdn.pixabay.com/photo/2021/04/29/21/23/laptop-6217523_1280.jpg', 'category_type': 'home'},
                {'name': 'Water Purifier Service', 'description': 'RO installation and filter replacement',
                 'image_url': 'https://images.unsplash.com/photo-1569373200232-5468a0cdc191?auto=format&fit=crop&fm=jpg&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&ixlib=rb-4.1.0&q=60&w=3000', 'category_type': 'home'},
            ]
            
            commercial_services = [
                {'name': 'Office Cleaning', 'description': 'Professional office cleaning services',
                 'image_url': 'https://cdn.pixabay.com/photo/2016/12/15/20/17/cleaning-1909978_1280.jpg', 'category_type': 'commercial'},
                {'name': 'Security Services', 'description': '24/7 security and surveillance',
                 'image_url': 'https://cdn.pixabay.com/photo/2017/12/19/20/42/security-3028679_1280.jpg', 'category_type': 'commercial'},
                {'name': 'Maintenance', 'description': 'Building and facility maintenance',
                 'image_url': 'https://cdn.pixabay.com/photo/2017/03/15/10/32/tools-2145770_1280.jpg', 'category_type': 'commercial'},
                {'name': 'Catering', 'description': 'Event and corporate catering',
                 'image_url': 'https://cdn.pixabay.com/photo/2019/11/14/11/10/chef-4625935_1280.jpg', 'category_type': 'commercial'},
                {'name': 'HVAC Maintenance', 'description': 'Commercial HVAC servicing and preventive maintenance',
                 'image_url': 'https://cdn.pixabay.com/photo/2021/12/14/07/34/worker-6869868_1280.jpg', 'category_type': 'commercial'},
                {'name': 'IT Network Setup', 'description': 'Office networking, CCTV, and system setup',
                 'image_url': 'https://cdn.pixabay.com/photo/2017/07/27/18/46/server-2546330_1280.jpg', 'category_type': 'commercial'},
                {'name': 'Deep Sanitization', 'description': 'Workplace sanitization and disinfection services',
                 'image_url': 'https://cdn.pixabay.com/photo/2020/04/26/04/38/disinfectant-5093503_1280.jpg', 'category_type': 'commercial'},
                {'name': 'Commercial Pest Management', 'description': 'Long-term pest management for business facilities',
                 'image_url': 'https://cdn.pixabay.com/photo/2020/04/26/04/38/disinfectant-5093503_1280.jpg', 'category_type': 'commercial'},
            ]
            
            db.service_categories.insert_many(home_services + commercial_services)
            
        admin = db.users.find_one({'email': ADMIN_EMAIL})
        if not admin:
            db.users.insert_one({
                'name': 'Admin',
                'email': ADMIN_EMAIL,
                'password_hash': generate_password_hash(ADMIN_PASSWORD),
                'is_admin': True
            })
    except Exception as e:
        print(f"Error during init_db: {e}")

if __name__ == '__main__':
    try:
        init_db()
    except Exception as e:
        print("MongoDB init failed:", e)
        print("Continuing startup anyway...")
    
    app.run(debug=True, port=5000)
