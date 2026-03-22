"""
Conect Us - Home Services Platform
Main Flask Application with MongoDB Integration
"""

from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify, send_from_directory, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import random
import os
import io
import traceback
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Load environment variables
load_dotenv()

from pymongo import MongoClient
from bson.objectid import ObjectId
import certifi
from authlib.integrations.flask_client import OAuth
import requests
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Initialize Flask app
app = Flask(__name__)
# Fix for Vercel/Proxy to use https and correct host in url_for
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

SECRET_KEY = os.environ.get('SECRET_KEY', 'conect-us-secret-key-change-in-production')
app.config['SECRET_KEY'] = SECRET_KEY
# Ensure sessions work well on Vercel/HTTPS
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

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

# PWA Configuration Routes
@app.route('/sw.js')
def sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/json')


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if db is None:
        return render_template('index.html', home_services=[], commercial_services=[])
        
    try:
        home_services = [to_dict_with_id(d) for d in db.service_categories.find({'category_type': 'home'})]
        commercial_services = [to_dict_with_id(d) for d in db.service_categories.find({'category_type': 'commercial'})]
    except:
        home_services = []
        commercial_services = []
        
    return render_template('index.html', home_services=home_services, commercial_services=commercial_services)


@app.route('/home')
def home():
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if db is None:
        flash("Database connection is down. Please try again later.", "error")
        return redirect(url_for('index'))
    try:
        home_services = [to_dict_with_id(d) for d in db.service_categories.find({'category_type': 'home'})]
        commercial_services = [to_dict_with_id(d) for d in db.service_categories.find({'category_type': 'commercial'})]
    except Exception as e:
        print(f"DB Error: {e}")
        flash("Could not load services. Check DB connection.", "error")
        return redirect(url_for('index'))
        
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
        if db is None:
            flash("Database connection error. Try again later.", "error")
            return render_template('login.html')
            
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        
        try:
            user_data = db.users.find_one({'email': email})
        except Exception as e:
            print(f"Login DB error: {e}")
            flash("Service unavailable. Try again later.", "error")
            return render_template('login.html')
        
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
        if db is None:
            return jsonify({'success': False, 'message': 'Database connection error. Try again later.'})
            
        name = request.form.get('name')
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone')
        password = request.form.get('password')

        if email == ADMIN_EMAIL:
            return jsonify({'success': False, 'message': 'This email is reserved and cannot be used for signup'})
        
        try:
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
        except Exception as e:
                print(f"OTP DB error: {e}")
                return jsonify({'success': False, 'message': 'Database operation failed.'})
        
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
            'email': email
        })
    return jsonify({'success': False, 'message': 'Invalid request'})


@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    if request.method == 'POST':
        if db is None:
            return jsonify({'success': False, 'message': 'Database unavailable.'})
            
        email = request.form.get('email')
        otp = request.form.get('otp')
        
        try:
            otp_record = db.otp_verifications.find_one({
                'email': email, 
                'otp_code': otp, 
                'is_verified': False
            })
            
            if not otp_record:
                return jsonify({'success': False, 'message': 'Invalid OTP'})
            
            # Note: Mongo dates are stored as naive UTC or BSON datetime. 
            # We must be careful with comparison. 
            expiry = otp_record.get('expires_at')
            if expiry:
                # Ensure we compare with offset-aware UTC
                if expiry.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
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
        except Exception as e:
            print(f"Verify OTP error: {e}")
            return jsonify({'success': False, 'message': 'Verification failed due to DB error.'})
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
            'message': 'New OTP sent successfully!'
        })
    return jsonify({'success': False, 'message': 'Invalid request'})


@app.route('/google_login')
def google_login():
    # Attempt to use the REDIRECT_URI from .env if available, otherwise fallback to url_for
    # Note: Google Console must have this exact URI registered.
    redirect_uri = os.environ.get('REDIRECT_URI')
    if not redirect_uri:
        # url_for will correctly use https thanks to ProxyFix
        redirect_uri = url_for('google_callback', _external=True)
        
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/login/callback')
def google_callback():
    if db is None:
        flash("Database connection error. Try logging in again later.", "error")
        return redirect(url_for('login'))
        
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
        print(f"Auth Error during token exchange: {e}")
        traceback.print_exc()
        flash(f'Google login failed: {str(e)}', 'error')
        
    return redirect(url_for('login'))


@app.route('/admin_secret_login', methods=['POST'])
def admin_secret_login():
    if db is None:
         return jsonify({'success': False, 'message': 'Database not connected'})
    pin = request.form.get('pin')
    if pin == "52623":
        admin_user_data = db.users.find_one({'email': ADMIN_EMAIL, 'is_admin': True})
        if not admin_user_data:
            # Auto-create admin if missing
            db.users.insert_one({
                'name': 'Admin',
                'email': ADMIN_EMAIL,
                'password_hash': generate_password_hash(ADMIN_PASSWORD),
                'is_admin': True
            })
            admin_user_data = db.users.find_one({'email': ADMIN_EMAIL, 'is_admin': True})
        
        user = User(admin_user_data)
        login_user(user)
        return jsonify({'success': True, 'redirect': url_for('admin_dashboard')})
    return jsonify({'success': False, 'message': 'Incorrect PIN'})


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/service/<service_id>')
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
    
    # Send Attractive Confirmation Email
    if FLASK_MAIL_AVAILABLE:
        try:
            msg = Message(
                subject=f'Booking Confirmed: {service_name} Request',
                recipients=[current_user.email]
            )
            msg.html = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background-color: #ffffff;">
                <div style="background-color: #111827; padding: 40px 20px; text-align: center; color: #ffffff;">
                    <h1 style="margin: 0; font-size: 32px; letter-spacing: 1px;">Conect Us</h1>
                    <p style="margin: 10px 0 0; opacity: 0.8; font-size: 16px;">Professional Home Services</p>
                </div>
                
                <div style="padding: 40px 30px;">
                    <h2 style="color: #1a1a2e; margin-top: 0; font-size: 24px;">Thank You for Your Booking!</h2>
                    <p style="color: #4b5563; font-size: 16px; line-height: 1.6;">Hello <strong>{current_user.name}</strong>,</p>
                    <p style="color: #4b5563; font-size: 16px; line-height: 1.6;">We've successfully received your request for <strong>{service_name}</strong>. Our team is currently reviewing your details and will get back to you shortly.</p>
                    
                    <div style="margin: 30px 0; background-color: #f9fafb; border-radius: 8px; padding: 25px; border-left: 4px solid #111827;">
                        <h3 style="margin-top: 0; color: #111827; font-size: 18px;">Booking Summary</h3>
                        <p style="margin: 8px 0; color: #374151;"><strong>Service:</strong> {service_name}</p>
                        <p style="margin: 8px 0; color: #374151;"><strong>Address:</strong> {address}</p>
                        <p style="margin: 8px 0; color: #374151;"><strong>Status:</strong> <span style="background-color: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">PENDING REVIEW</span></p>
                    </div>
                    
                    <div style="text-align: center; margin-top: 40px;">
                        <a href="{url_for('my_bookings', _external=True)}" style="background-color: #111827; color: #ffffff; text-decoration: none; padding: 15px 30px; border-radius: 30px; font-weight: 600; display: inline-block;">View My Bookings</a>
                    </div>
                </div>
                
                <div style="background-color: #f3f4f6; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                    <p style="margin: 0; color: #6b7280; font-size: 14px;">Need help? Reply to this email or visit our Help Center.</p>
                    <p style="margin: 10px 0 0; color: #9ca3af; font-size: 12px;">© {datetime.now().year} Conect Us Home Services. All Rights Reserved.</p>
                </div>
            </div>
            """
            mail.send(msg)
        except Exception as e:
            print(f"Failed to send booking confirmation email: {e}")

    flash('Service booked successfully! A confirmation email has been sent to you.', 'success')
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
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1':
            return jsonify({'success': True, 'message': f'Booking {status_map[action]}'})
        flash(f'Booking {status_map[action]} successfully!', 'success')
    
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/booking_pdf/<booking_id>')
@login_required
def booking_pdf(booking_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))

    try:
        bid = ObjectId(booking_id)
    except:
        bid = booking_id

    booking = db.booking_requests.find_one({'_id': bid})
    if not booking:
        flash('Booking not found', 'error')
        return redirect(url_for('admin_dashboard'))

    booking = to_dict_with_id(booking)

    # Use io.BytesIO to create the PDF in memory
    buffer = io.BytesIO()
    
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor("#111827"),
        spaceAfter=20,
        alignment=0 # Left
    )
    
    label_style = ParagraphStyle(
        'LabelStyle',
        parent=styles['Normal'],
        fontSize=11,
        fontName='Helvetica-Bold'
    )
    
    value_style = ParagraphStyle(
        'ValueStyle',
        parent=styles['Normal'],
        fontSize=11,
        fontName='Helvetica'
    )

    content = []
    
    # Colorful Header: Full Width Brand Background
    title_style_pdf = ParagraphStyle(
        'TitleStylePDF',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.white,
        alignment=1, # Center
        spaceAfter=15,
        fontName='Helvetica-Bold'
    )
    
    id_style_pdf = ParagraphStyle(
        'IdStylePDF',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.whitesmoke,
        alignment=1, # Center
        fontName='Helvetica'
    )

    # Header with colorful background
    header_table_data = [
        [Paragraph("Conect Us", title_style_pdf)],
        [Paragraph(f"BOOKING REQUEST ID: {booking['id'][:12].upper()}", id_style_pdf)]
    ]
    
    header_table_full = Table(header_table_data, colWidths=[doc.width + doc.leftMargin + doc.rightMargin])
    header_table_full.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#111827")),
        ('TOPPADDING', (0, 0), (-1, -1), 30),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 30),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    # We need to use a slightly wider table to cover the whole page width or adjust margins
    # Let's stick to the doc width for safety or use negative margins if DocTemplate allows
    content.append(header_table_full)
    content.append(Spacer(1, 25))

    # Section headers with colorful accent
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor("#111827"),
        spaceAfter=10,
        borderPadding=(0, 0, 5, 0),
        borderWidth=0,
        borderColor=colors.HexColor("#111827")
    )
    
    # Thinner and brand-colored horizontal line
    from reportlab.platypus import HRFlowable
    content.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#111827"), spaceAfter=25))
    
    # Custom Styles for Colorful Table
    label_style_white = ParagraphStyle(
        'LabelStyleWhite',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.white,
        fontName='Helvetica-Bold'
    )
    
    # Status-specific color
    status_text = booking.get('status', 'pending').lower()
    status_color = colors.HexColor("#111827") # Default
    if status_text in ['accepted', 'completed']:
        status_color = colors.HexColor("#10b981") # Green
    elif status_text == 'pending':
        status_color = colors.HexColor("#f59e0b") # Amber

    # Main Info Table with vibrant headers
    info_data = [
        [Paragraph("Service Category", label_style_white), Paragraph(booking.get('service_name', 'N/A'), value_style)],
        [Paragraph("Booking Status", label_style_white), Paragraph(f"<b>{booking.get('status', 'pending').upper()}</b>", ParagraphStyle('StatusStyle', parent=value_style, textColor=status_color))],
        [Paragraph("Date Requested", label_style_white), Paragraph(booking.get('created_at').strftime('%Y-%m-%d %H:%M') if booking.get('created_at') else 'N/A', value_style)],
    ]
    
    info_table = Table(info_data, colWidths=[2.2*inch, 4.3*inch], rowHeights=35)
    info_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#111827")),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#111827")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
    ]))
    
    content.append(Paragraph("Booking Details", section_style))
    content.append(Spacer(1, 10))
    content.append(info_table)
    content.append(Spacer(1, 20))
    
    # Customer Table with vibrant headers
    customer_data = [
        [Paragraph("Customer Name", label_style_white), Paragraph(booking.get('user_name', 'N/A'), value_style)],
        [Paragraph("Email Address", label_style_white), Paragraph(booking.get('user_email', 'N/A'), value_style)],
        [Paragraph("Phone Number", label_style_white), Paragraph(booking.get('user_phone', 'N/A'), value_style)],
        [Paragraph("Full Address", label_style_white), Paragraph(booking.get('address', 'N/A'), value_style)],
    ]
    
    customer_table = Table(customer_data, colWidths=[2.2*inch, 4.3*inch], rowHeights=None)
    customer_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#111827")),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#1d293f")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
    ]))
    
    content.append(Paragraph("Customer Information", section_style))
    content.append(Spacer(1, 10))
    content.append(customer_table)
    content.append(Spacer(1, 25))
    
    # Description
    content.append(Paragraph("Work Description", section_style))
    content.append(Spacer(1, 8))
    content.append(Paragraph(booking.get('description') or 'No description provided.', value_style))
    content.append(Spacer(1, 40))
    
    # Centered Footer Function (updated with more color/style)
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#111827"))
        canvas.setLineWidth(2)
        canvas.line(0.5*inch, 0.95*inch, A4[0]-0.5*inch, 0.95*inch)
        
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.HexColor("#111827"))
        canvas.drawString(0.5*inch, 0.75 * inch, f"© {datetime.now().year} Conect Us Home Services Platform")
        canvas.drawRightString(A4[0] - 0.5*inch, 0.75 * inch, f"Official Service Document - Page {doc.page}")
        canvas.restoreState()

    doc.build(content, onFirstPage=add_footer, onLaterPages=add_footer)
    
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"booking-request-{booking['id'][:8]}.pdf"
    )

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
