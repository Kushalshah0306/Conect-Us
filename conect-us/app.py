"""
Conect Us - Home Services Platform
Main Flask Application
"""

from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import random
import os

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'conect-us-secret-key-change-in-production'

def _get_database_uri():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return db_url
    if os.environ.get('VERCEL'):
        # Vercel filesystem is read-only except /tmp
        return 'sqlite:////tmp/conectus.db'
    return 'sqlite:///conectus.db'

app.config['SQLALCHEMY_DATABASE_URI'] = _get_database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fixed admin credentials
ADMIN_EMAIL = 'admin@conectus.com'
ADMIN_PASSWORD = 'Admin@123'

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Flask-Mail (optional - for sending OTP emails)
# For Gmail: Use App Password (16 chars) - Enable 2FA and create App Password at myaccount.google.com/signinoptions/two-step-verification
try:
    from flask_mail import Mail, Message
    
    # Use environment variables for email credentials (more secure)
    # For Gmail, you need an App Password (not your regular password)
    # Get it from: https://myaccount.google.com/signinoptions/two-step-verification
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'noreply@conectus.com')
    
    mail = Mail(app)
    FLASK_MAIL_AVAILABLE = True
    print(f"Flask-Mail configured for: {app.config['MAIL_SERVER']}")
except ImportError:
    mail = None
    FLASK_MAIL_AVAILABLE = False
    print("Flask-Mail not installed. Email OTP will not work.")

# Database Models

class User(UserMixin, db.Model):
    """User model for authentication"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    
class ServiceCategory(db.Model):
    """Service category model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(200))
    category_type = db.Column(db.String(50))  # 'home' or 'commercial'
    
class ServiceSubCategory(db.Model):
    """Service subcategory model"""
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('service_category.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(200))
    price_start = db.Column(db.Integer, default=0)
    
class BookingRequest(db.Model):
    """Model for user service requests"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service_sub_category.id'), nullable=False)
    service_name = db.Column(db.String(100))
    user_name = db.Column(db.String(100))
    user_email = db.Column(db.String(150))
    user_phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    description = db.Column(db.Text)
    latitude = db.Column(db.Float, nullable=True)  # User's live location latitude
    longitude = db.Column(db.Float, nullable=True)  # User's live location longitude
    status = db.Column(db.String(50), default='pending')  # pending, accepted, completed, cancelled
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class OTPVerification(db.Model):
    """Model for OTP verification"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), nullable=False)
    otp_code = db.Column(db.String(6), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    expires_at = db.Column(db.DateTime, nullable=False)
    is_verified = db.Column(db.Boolean, default=False)

# User loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes

@app.route('/')
def index():
    """Home page - shows landing page before login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    """Handle browser favicon requests to avoid 404 logs."""
    return '', 204

@app.route('/home')
def home():
    """Home page for logged in users"""
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard with services"""
    home_services = ServiceCategory.query.filter_by(category_type='home').all()
    commercial_services = ServiceCategory.query.filter_by(category_type='commercial').all()
    return render_template('dashboard.html', 
                           home_services=home_services, 
                           commercial_services=commercial_services)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
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
    """Signup page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone')
        password = request.form.get('password')

        if email == ADMIN_EMAIL:
            flash('This email is reserved and cannot be used for signup.', 'error')
            return redirect(url_for('signup'))
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('signup'))
        
        # Always create normal users from signup
        hashed_password = generate_password_hash(password)
        new_user = User(name=name, email=email, phone=phone, password_hash=hashed_password, is_admin=False)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/send_otp', methods=['POST'])
def send_otp():
    """Send OTP to user's email"""
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone')
        password = request.form.get('password')

        if email == ADMIN_EMAIL:
            return jsonify({'success': False, 'message': 'This email is reserved and cannot be used for signup'})
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Email already registered'})
        
        # Check if there's already a pending OTP for this email
        existing_otp = OTPVerification.query.filter_by(email=email, is_verified=False).first()
        if existing_otp:
            # Delete old OTP
            db.session.delete(existing_otp)
            db.session.commit()
        
        # Generate 6-digit OTP
        otp_code = str(random.randint(100000, 999999))
        
        # Calculate expiry time (5 minutes)
        from datetime import timezone
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        # Hash the password
        hashed_password = generate_password_hash(password)
        is_admin = False
        
        # Store OTP with user details
        otp_record = OTPVerification(
            email=email,
            otp_code=otp_code,
            name=name,
            phone=phone,
            password_hash=hashed_password,
            is_admin=is_admin,
            expires_at=expires_at
        )
        db.session.add(otp_record)
        db.session.commit()
        
        # Try to send OTP via email if available
        if FLASK_MAIL_AVAILABLE:
            try:
                send_otp_email(email, otp_code, name)
            except Exception as e:
                print(f"Email sending failed: {e}")
        
        return jsonify({
            'success': True, 
            'message': 'OTP sent successfully!',
            'email': email,
            'otp': otp_code  # Remove this in production
        })
    
    return jsonify({'success': False, 'message': 'Invalid request'})

def send_otp_email(email, otp_code, name):
    """Send OTP via email"""
    if not FLASK_MAIL_AVAILABLE:
        return False
    try:
        msg = Message(
            subject='Your Conect Us Verification Code',
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )
        msg.body = f"""
Hello {name},

Your verification code is: {otp_code}

This code will expire in 5 minutes.

If you didn't request this, please ignore this email.

Best regards,
Conect Us Team
"""
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    """Verify OTP and create user account"""
    if request.method == 'POST':
        email = request.form.get('email')
        otp = request.form.get('otp')
        
        # Find the OTP record
        otp_record = OTPVerification.query.filter_by(email=email, otp_code=otp, is_verified=False).first()
        
        if not otp_record:
            return jsonify({'success': False, 'message': 'Invalid OTP'})
        
        # Check if OTP is expired
        if otp_record.expires_at < datetime.utcnow():
            db.session.delete(otp_record)
            db.session.commit()
            return jsonify({'success': False, 'message': 'OTP has expired. Please request a new one.'})
        
        # Mark OTP as verified
        otp_record.is_verified = True
        db.session.commit()
        
        # Create the user
        new_user = User(
            name=otp_record.name,
            email=otp_record.email,
            phone=otp_record.phone,
            password_hash=otp_record.password_hash,
            is_admin=otp_record.is_admin
        )
        db.session.add(new_user)
        db.session.commit()
        
        # Clean up OTP record
        db.session.delete(otp_record)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Account created successfully!'})
    
    return jsonify({'success': False, 'message': 'Invalid request'})

@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    """Resend OTP to user's email"""
    if request.method == 'POST':
        email = request.form.get('email')
        
        # Find existing OTP record
        otp_record = OTPVerification.query.filter_by(email=email, is_verified=False).first()
        
        if not otp_record:
            return jsonify({'success': False, 'message': 'No pending registration found. Please register again.'})
        
        # Generate new OTP
        otp_code = str(random.randint(100000, 999999))
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        
        otp_record.otp_code = otp_code
        otp_record.expires_at = expires_at
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'New OTP sent successfully!',
            'otp': otp_code  # Remove this in production
        })
    
    return jsonify({'success': False, 'message': 'Invalid request'})

@app.route('/google_login')
def google_login():
    """Google OAuth login - placeholder for implementation"""
    flash('Google login coming soon! Please use email/password for now.', 'info')
    return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    return redirect(url_for('index'))

@app.route('/service/<int:service_id>')
@login_required
def service_detail(service_id):
    """Service detail page"""
    service = ServiceCategory.query.get_or_404(service_id)
    sub_services = ServiceSubCategory.query.filter_by(category_id=service_id).all()
    return render_template('service_detail.html', service=service, sub_services=sub_services)

@app.route('/book_service', methods=['POST'])
@login_required
def book_service():
    """Book a service"""
    service_id = request.form.get('service_id')
    service_name = request.form.get('service_name')
    address = request.form.get('address')
    description = request.form.get('description')
    phone = request.form.get('phone')
    
    # Get latitude and longitude from form (live location)
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    
    booking = BookingRequest(
        user_id=current_user.id,
        service_id=service_id,
        service_name=service_name,
        user_name=current_user.name,
        user_email=current_user.email,
        user_phone=phone,
        address=address,
        description=description,
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None
    )
    db.session.add(booking)
    db.session.commit()
    
    flash('Service booked successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/my_bookings')
@login_required
def my_bookings():
    """View user's bookings"""
    bookings = BookingRequest.query.filter_by(user_id=current_user.id).order_by(BookingRequest.created_at.desc()).all()
    return render_template('my_bookings.html', bookings=bookings)

# Admin Routes

@app.route('/admin')
def admin():
    """Admin login page"""
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/admin_login.html')

@app.route('/admin_login', methods=['POST'])
def admin_login_post():
    """Admin login handler"""
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password')

    if email != ADMIN_EMAIL:
        flash('Invalid admin credentials', 'error')
        return redirect(url_for('admin'))

    user = User.query.filter_by(email=ADMIN_EMAIL, is_admin=True).first()

    if user and check_password_hash(user.password_hash, password):
        login_user(user)
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Invalid admin credentials', 'error')
        return redirect(url_for('admin'))

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard"""
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    all_bookings = BookingRequest.query.order_by(BookingRequest.created_at.desc()).all()
    return render_template('admin/admin_dashboard.html', bookings=all_bookings)

@app.route('/admin/client_activities')
@login_required
def client_activities():
    """View all client activities"""
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all users (clients)
    clients = User.query.filter_by(is_admin=False).all()
    
    # Get all bookings with user details
    all_bookings = BookingRequest.query.order_by(BookingRequest.created_at.desc()).all()
    
    # Get statistics
    total_clients = len(clients)
    total_bookings = len(all_bookings)
    pending_bookings = BookingRequest.query.filter_by(status='pending').count()
    completed_bookings = BookingRequest.query.filter_by(status='completed').count()
    
    return render_template('admin/client_activities.html', 
                         clients=clients, 
                         bookings=all_bookings,
                         total_clients=total_clients,
                         total_bookings=total_bookings,
                         pending_bookings=pending_bookings,
                         completed_bookings=completed_bookings)

@app.route('/admin/update_booking/<int:booking_id>/<action>')
@login_required
def update_booking(booking_id, action):
    """Update booking status"""
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    booking = BookingRequest.query.get_or_404(booking_id)
    
    if action == 'accept':
        booking.status = 'accepted'
    elif action == 'complete':
        booking.status = 'completed'
    elif action == 'cancel':
        booking.status = 'cancelled'
    
    db.session.commit()
    flash(f'Booking {action}ed successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

# Initialize database and create default data
def init_db(drop_all=False):
    """Initialize database with default services"""
    with app.app_context():
        # Optionally reset schema (useful for local development)
        if drop_all:
            db.drop_all()
        db.create_all()
        
        # Check if services already exist
        services_exist = ServiceCategory.query.first() is not None
        
        if not services_exist:
            # Home Services
            home_services = [
                ServiceCategory(name='Plumber', description='Fix leaks, pipe fitting, and plumbing issues', 
                              image_url='https://cdn.pixabay.com/photo/2017/09/26/11/10/plumber-2788332_1280.jpg', category_type='home'),
                ServiceCategory(name='Electrician', description='Electrical repairs and installations',
                              image_url='https://cdn.pixabay.com/photo/2015/05/01/18/13/electrician-748832_1280.jpg', category_type='home'),
                ServiceCategory(name='Carpenter', description='Furniture repair and custom carpentry',
                              image_url='https://cdn.pixabay.com/photo/2022/04/14/05/54/carpenter-7131654_1280.jpg', category_type='home'),
                ServiceCategory(name='House Cleaning', description='Deep cleaning and regular housekeeping',
                              image_url='https://cdn.pixabay.com/photo/2019/04/02/18/16/cleaning-4098410_1280.jpg', category_type='home'),
                ServiceCategory(name='AC Repair', description='Air conditioner service and repair',
                              image_url='https://cdn.pixabay.com/photo/2021/12/14/07/34/worker-6869868_1280.jpg', category_type='home'),
                ServiceCategory(name='Pest Control', description='Pest extermination services',
                              image_url='https://cdn.pixabay.com/photo/2020/04/26/04/38/disinfectant-5093503_1280.jpg', category_type='home'),
                ServiceCategory(name='Painting', description='Interior and exterior wall painting',
                              image_url='https://cdn.pixabay.com/photo/2017/09/15/10/24/painter-2751662_1280.jpg', category_type='home'),
                ServiceCategory(name='Appliance Repair', description='Repair service for home appliances',
                              image_url='https://cdn.pixabay.com/photo/2021/04/29/21/23/laptop-6217523_1280.jpg', category_type='home'),
                ServiceCategory(name='Water Purifier Service', description='RO installation and filter replacement',
                              image_url='https://images.unsplash.com/photo-1569373200232-5468a0cdc191?auto=format&fit=crop&fm=jpg&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&ixlib=rb-4.1.0&q=60&w=3000', category_type='home'),
            ]
            
            # Commercial Services
            commercial_services = [
                ServiceCategory(name='Office Cleaning', description='Professional office cleaning services',
                              image_url='https://cdn.pixabay.com/photo/2016/12/15/20/17/cleaning-1909978_1280.jpg', category_type='commercial'),
                ServiceCategory(name='Security Services', description='24/7 security and surveillance',
                              image_url='https://cdn.pixabay.com/photo/2017/12/19/20/42/security-3028679_1280.jpg', category_type='commercial'),
                ServiceCategory(name='Maintenance', description='Building and facility maintenance',
                              image_url='https://cdn.pixabay.com/photo/2017/03/15/10/32/tools-2145770_1280.jpg', category_type='commercial'),
                ServiceCategory(name='Catering', description='Event and corporate catering',
                              image_url='https://cdn.pixabay.com/photo/2019/11/14/11/10/chef-4625935_1280.jpg', category_type='commercial'),
                ServiceCategory(name='HVAC Maintenance', description='Commercial HVAC servicing and preventive maintenance',
                              image_url='https://cdn.pixabay.com/photo/2021/12/14/07/34/worker-6869868_1280.jpg', category_type='commercial'),
                ServiceCategory(name='IT Network Setup', description='Office networking, CCTV, and system setup',
                              image_url='https://cdn.pixabay.com/photo/2017/07/27/18/46/server-2546330_1280.jpg', category_type='commercial'),
                ServiceCategory(name='Deep Sanitization', description='Workplace sanitization and disinfection services',
                              image_url='https://cdn.pixabay.com/photo/2020/04/26/04/38/disinfectant-5093503_1280.jpg', category_type='commercial'),
                ServiceCategory(name='Commercial Pest Management', description='Long-term pest management for business facilities',
                              image_url='https://cdn.pixabay.com/photo/2020/04/26/04/38/disinfectant-5093503_1280.jpg', category_type='commercial'),
            ]
            
            for service in home_services + commercial_services:
                db.session.add(service)
            
            db.session.commit()
        
        # Create/update fixed admin user
        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        if not admin:
            admin = User(
                name='Admin',
                email=ADMIN_EMAIL,
                password_hash=generate_password_hash(ADMIN_PASSWORD),
                is_admin=True
            )
            db.session.add(admin)
        else:
            admin.name = 'Admin'
            admin.is_admin = True
            admin.password_hash = generate_password_hash(ADMIN_PASSWORD)
        db.session.commit()

if __name__ == '__main__':
    init_db(drop_all=True)
    app.run(debug=True, port=5000)

