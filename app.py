#!/usr/bin/env python3
"""
Multi-Tenant CMDB Application
Main application entry point
"""

import os
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:////app/data/cmdb.sqlite')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


# ==================== Database Models ====================

class Tenant(db.Model):
    """Tenant/Organization model for multi-tenancy"""
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    users = db.relationship('User', backref='tenant', lazy='dynamic')
    ci_types = db.relationship('CIType', backref='tenant', lazy='dynamic', cascade='all, delete-orphan')
    config_items = db.relationship('ConfigItem', backref='tenant', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Tenant {self.name}>'


class User(UserMixin, db.Model):
    """User model with tenant association"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_owner = db.Column(db.Boolean, default=False)  # Can manage CI types and fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class CIType(db.Model):
    """Configuration Item Type definition per tenant"""
    __tablename__ = 'ci_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # User who owns this CI type
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    config_items = db.relationship('ConfigItem', backref='ci_type', lazy='dynamic')
    fields = db.relationship('CITypeField', backref='ci_type', lazy='dynamic', cascade='all, delete-orphan')
    owner = db.relationship('User', backref='owned_ci_types')

    __table_args__ = (db.UniqueConstraint('name', 'tenant_id', name='unique_ci_type_per_tenant'),)

    def __repr__(self):
        return f'<CIType {self.name}>'


class ConfigItem(db.Model):
    """Configuration Item - the actual CMDB entries"""
    __tablename__ = 'config_items'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    ci_type_id = db.Column(db.Integer, db.ForeignKey('ci_types.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    status = db.Column(db.String(50), default='active')  # active, retired, maintenance, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    creator = db.relationship('User', backref='created_items')
    relationships = db.relationship('CIRelationship', foreign_keys='CIRelationship.source_ci_id', backref='source')
    dependent_relationships = db.relationship('CIRelationship', foreign_keys='CIRelationship.target_ci_id', backref='target')
    field_values = db.relationship('CIFieldValue', backref='config_item', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ConfigItem {self.name}>'


class CIStatus(db.Model):
    """Custom status definitions for Config Items per tenant"""
    __tablename__ = 'ci_statuses'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    label = db.Column(db.String(50), nullable=False)  # Display name
    color = db.Column(db.String(20), default='info')  # success, warning, danger, info, secondary
    is_default = db.Column(db.Boolean, default=False)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    tenant = db.relationship('Tenant', backref='statuses')

    __table_args__ = (db.UniqueConstraint('tenant_id', 'name', name='unique_status_per_tenant'),)

    def __repr__(self):
        return f'<CIStatus {self.name}>'


class CIRelationship(db.Model):
    """Relationships between Configuration Items"""
    __tablename__ = 'ci_relationships'

    id = db.Column(db.Integer, primary_key=True)
    source_ci_id = db.Column(db.Integer, db.ForeignKey('config_items.id'), nullable=False)
    target_ci_id = db.Column(db.Integer, db.ForeignKey('config_items.id'), nullable=False)
    relationship_type = db.Column(db.String(50), nullable=False)  # depends_on, hosted_on, connected_to, etc.
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('source_ci_id', 'target_ci_id', 'relationship_type', name='unique_relationship'),)

    def __repr__(self):
        return f'<CIRelationship {self.relationship_type}>'


class CIHistory(db.Model):
    """History/Audit trail for Configuration Item changes"""
    __tablename__ = 'ci_history'

    id = db.Column(db.Integer, primary_key=True)
    ci_id = db.Column(db.Integer, db.ForeignKey('config_items.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # created, updated, status_changed, deleted
    field_name = db.Column(db.String(100))  # Which field was changed
    old_value = db.Column(db.Text)  # Previous value (JSON string)
    new_value = db.Column(db.Text)  # New value (JSON string)
    comment = db.Column(db.Text)  # Optional comment about the change
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    config_item = db.relationship('ConfigItem', backref='history')
    user = db.relationship('User', backref='history_changes')

    def __repr__(self):
        return f'<CIHistory {self.action} on CI {self.ci_id}>'


class CITypeField(db.Model):
    """Custom field definition for a CI Type"""
    __tablename__ = 'ci_type_fields'

    id = db.Column(db.Integer, primary_key=True)
    ci_type_id = db.Column(db.Integer, db.ForeignKey('ci_types.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    label = db.Column(db.String(100), nullable=False)  # Display name
    field_type = db.Column(db.String(50), nullable=False)  # text, number, email, url, date, select, boolean
    is_required = db.Column(db.Boolean, default=False)
    default_value = db.Column(db.Text)
    options = db.Column(db.Text)  # JSON array for select options
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    field_values = db.relationship('CIFieldValue', backref='field', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (db.UniqueConstraint('ci_type_id', 'name', name='unique_field_per_ci_type'),)

    def __repr__(self):
        return f'<CITypeField {self.name}>'


class CIFieldValue(db.Model):
    """Value of a custom field for a specific Config Item"""
    __tablename__ = 'ci_field_values'

    id = db.Column(db.Integer, primary_key=True)
    ci_id = db.Column(db.Integer, db.ForeignKey('config_items.id'), nullable=False)
    field_id = db.Column(db.Integer, db.ForeignKey('ci_type_fields.id'), nullable=False)
    value_text = db.Column(db.Text)  # Stores the field value

    def __repr__(self):
        return f'<CIFieldValue CI:{self.ci_id} Field:{self.field_id}>'


# ==================== Login Manager ====================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==================== Custom Decorators ====================

def tenant_required(f):
    """Decorator to ensure user has a tenant"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.tenant:
            flash('Please select or create a tenant.', 'warning')
            return redirect(url_for('select_tenant'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to restrict access to admin users only"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def owner_required(f):
    """Decorator to restrict access to owner or admin users only"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in.', 'error')
            return redirect(url_for('login'))
        if not (current_user.is_admin or current_user.is_owner):
            flash('Owner access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def ci_type_owner_or_admin(ci_type_id_param='ci_type_id'):
    """Decorator to check if user owns the specific CI type or is admin"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in.', 'error')
                return redirect(url_for('login'))
            if current_user.is_admin:
                return f(*args, **kwargs)
            
            ci_type_id = kwargs.get(ci_type_id_param)
            if ci_type_id:
                ci_type = CIType.query.get(int(ci_type_id))
                if ci_type and ci_type.owner_id == current_user.id:
                    return f(*args, **kwargs)
            
            flash('You do not have permission to manage this CI type.', 'error')
            return redirect(url_for('dashboard'))
        return decorated_function
    return decorator


# ==================== Routes ====================

@app.route('/')
def index():
    """Home page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash('Logged in successfully!', 'success')
            return redirect(next_page if next_page else url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration with new tenant creation"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        tenant_name = request.form.get('tenant_name')
        
        # Validation
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('register.html')
        
        # Create tenant and user
        tenant = Tenant(name=tenant_name, description=f'Tenant for {username}')
        db.session.add(tenant)
        db.session.flush()  # Get tenant ID
        
        user = User(
            username=username,
            email=email,
            tenant_id=tenant.id,
            is_admin=True  # First user is admin
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/dashboard')
@login_required
@tenant_required
def dashboard():
    """Main dashboard"""
    # Get stats for current tenant
    ci_count = ConfigItem.query.filter_by(tenant_id=current_user.tenant_id).count()
    ci_type_count = CIType.query.filter_by(tenant_id=current_user.tenant_id).count()
    recent_items = ConfigItem.query.filter_by(
        tenant_id=current_user.tenant_id
    ).order_by(ConfigItem.created_at.desc()).limit(5).all()
    
    return render_template('dashboard.html', 
                         ci_count=ci_count, 
                         ci_type_count=ci_type_count,
                         recent_items=recent_items)


@app.route('/tenants')
@login_required
def select_tenant():
    """Tenant selection page for users with multiple tenants"""
    tenants = Tenant.query.filter_by(is_active=True).all()
    return render_template('tenants.html', tenants=tenants)


@app.route('/tenants/<int:tenant_id>/switch')
@login_required
def switch_tenant(tenant_id):
    """Switch to a different tenant (for admin users)"""
    tenant = Tenant.query.get_or_404(tenant_id)
    # In a real app, you'd store this in session
    flash(f'Switched to tenant: {tenant.name}', 'success')
    return redirect(url_for('dashboard'))


# ==================== CI Type Routes ====================

@app.route('/ci-types')
@login_required
@tenant_required
def list_ci_types():
    """List all CI types for current tenant"""
    ci_types = CIType.query.filter_by(tenant_id=current_user.tenant_id).all()
    return render_template('ci_types/list.html', ci_types=ci_types)


@app.route('/ci-types/new', methods=['GET', 'POST'])
@login_required
@tenant_required
@admin_required
def create_ci_type():
    """Create new CI type"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        # Check for duplicates
        existing = CIType.query.filter_by(
            name=name, 
            tenant_id=current_user.tenant_id
        ).first()
        
        if existing:
            flash('CI Type with this name already exists.', 'error')
            return render_template('ci_types/form.html')
        
        ci_type = CIType(
            name=name,
            description=description,
            tenant_id=current_user.tenant_id,
            owner_id=current_user.id  # Creator becomes owner
        )
        db.session.add(ci_type)
        db.session.commit()

        flash('CI Type created successfully!', 'success')
        return redirect(url_for('list_ci_types'))
    
    return render_template('ci_types/form.html')


@app.route('/ci-types/<int:ci_type_id>')
@login_required
@tenant_required
def view_ci_type(ci_type_id):
    """View CI type details"""
    ci_type = CIType.query.filter_by(
        id=ci_type_id, 
        tenant_id=current_user.tenant_id
    ).first_or_404()
    
    config_items = ConfigItem.query.filter_by(ci_type_id=ci_type_id).all()
    return render_template('ci_types/view.html', ci_type=ci_type, config_items=config_items)


@app.route('/ci-types/<int:ci_type_id>/edit', methods=['GET', 'POST'])
@login_required
@tenant_required
@ci_type_owner_or_admin()
def edit_ci_type(ci_type_id):
    """Edit CI type"""
    ci_type = CIType.query.filter_by(
        id=ci_type_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()

    if request.method == 'POST':
        ci_type.name = request.form.get('name')
        ci_type.description = request.form.get('description')
        db.session.commit()

        flash('CI Type updated successfully!', 'success')
        return redirect(url_for('view_ci_type', ci_type_id=ci_type.id))

    return render_template('ci_types/form.html', ci_type=ci_type)


@app.route('/ci-types/<int:ci_type_id>/delete', methods=['POST'])
@login_required
@tenant_required
@ci_type_owner_or_admin()
def delete_ci_type(ci_type_id):
    """Delete CI type"""
    ci_type = CIType.query.filter_by(
        id=ci_type_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()

    db.session.delete(ci_type)
    db.session.commit()

    flash('CI Type deleted successfully!', 'success')
    return redirect(url_for('list_ci_types'))


# ==================== CI Type Field Routes ====================

@app.route('/ci-types/<int:ci_type_id>/fields')
@login_required
@tenant_required
def list_ci_type_fields(ci_type_id):
    """List all fields for a CI type"""
    ci_type = CIType.query.filter_by(
        id=ci_type_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()
    
    fields = CITypeField.query.filter_by(ci_type_id=ci_type_id).order_by(CITypeField.display_order).all()
    is_owner = current_user.is_admin or (ci_type.owner_id == current_user.id)
    
    return render_template('ci_types/fields.html', ci_type=ci_type, fields=fields, is_owner=is_owner)


@app.route('/ci-types/<int:ci_type_id>/fields/new', methods=['GET', 'POST'])
@login_required
@tenant_required
@ci_type_owner_or_admin()
def create_ci_type_field(ci_type_id):
    """Create new field for a CI type"""
    ci_type = CIType.query.filter_by(
        id=ci_type_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()
    
    if request.method == 'POST':
        name = request.form.get('name')
        label = request.form.get('label')
        field_type = request.form.get('field_type', 'text')
        is_required = request.form.get('is_required') == 'on'
        default_value = request.form.get('default_value')
        options = request.form.get('options')  # Comma-separated for select
        display_order = request.form.get('display_order', 0, type=int)
        
        # Check for duplicate field names
        existing = CITypeField.query.filter_by(
            ci_type_id=ci_type_id,
            name=name
        ).first()
        
        if existing:
            flash('Field with this name already exists.', 'error')
            return render_template('ci_types/field_form.html', ci_type=ci_type)
        
        field = CITypeField(
            ci_type_id=ci_type_id,
            name=name,
            label=label,
            field_type=field_type,
            is_required=is_required,
            default_value=default_value,
            options=options,
            display_order=display_order
        )
        db.session.add(field)
        db.session.commit()
        
        flash('Field created successfully!', 'success')
        return redirect(url_for('list_ci_type_fields', ci_type_id=ci_type_id))
    
    return render_template('ci_types/field_form.html', ci_type=ci_type)


@app.route('/fields/<int:field_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_ci_type_field(field_id):
    """Edit CI type field"""
    field = CITypeField.query.get_or_404(field_id)
    ci_type = CIType.query.filter_by(
        id=field.ci_type_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()
    
    # Check ownership
    if not (current_user.is_admin or ci_type.owner_id == current_user.id):
        flash('You do not have permission to edit this field.', 'error')
        return redirect(url_for('list_ci_type_fields', ci_type_id=ci_type_id))
    
    if request.method == 'POST':
        field.name = request.form.get('name')
        field.label = request.form.get('label')
        field.field_type = request.form.get('field_type', 'text')
        field.is_required = request.form.get('is_required') == 'on'
        field.default_value = request.form.get('default_value')
        field.options = request.form.get('options')
        field.display_order = request.form.get('display_order', 0, type=int)
        db.session.commit()
        
        flash('Field updated successfully!', 'success')
        return redirect(url_for('list_ci_type_fields', ci_type_id=ci_type.id))
    
    return render_template('ci_types/field_form.html', ci_type=ci_type, field=field)


@app.route('/fields/<int:field_id>/delete', methods=['POST'])
@login_required
def delete_ci_type_field(field_id):
    """Delete CI type field"""
    field = CITypeField.query.get_or_404(field_id)
    ci_type = CIType.query.filter_by(
        id=field.ci_type_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()
    
    # Check ownership
    if not (current_user.is_admin or ci_type.owner_id == current_user.id):
        flash('You do not have permission to delete this field.', 'error')
        return redirect(url_for('list_ci_type_fields', ci_type_id=ci_type_id))
    
    db.session.delete(field)
    db.session.commit()
    
    flash('Field deleted successfully!', 'success')
    return redirect(url_for('list_ci_type_fields', ci_type_id=ci_type.id))


# ==================== CI Status Routes ====================

@app.route('/statuses')
@login_required
@tenant_required
def list_statuses():
    """List all statuses for current tenant"""
    statuses = CIStatus.query.filter_by(tenant_id=current_user.tenant_id).order_by(CIStatus.display_order).all()
    return render_template('statuses/list.html', statuses=statuses)


@app.route('/statuses/new', methods=['GET', 'POST'])
@login_required
@tenant_required
@owner_required
def create_status():
    """Create new status"""
    if request.method == 'POST':
        name = request.form.get('name')
        label = request.form.get('label')
        color = request.form.get('color', 'info')
        is_default = request.form.get('is_default') == 'on'
        display_order = request.form.get('display_order', 0, type=int)

        # Check for duplicate
        existing = CIStatus.query.filter_by(
            name=name,
            tenant_id=current_user.tenant_id
        ).first()

        if existing:
            flash('Status with this name already exists.', 'error')
            return render_template('statuses/form.html')

        # If this is default, unset others
        if is_default:
            CIStatus.query.filter_by(
                tenant_id=current_user.tenant_id,
                is_default=True
            ).update({'is_default': False})

        status = CIStatus(
            name=name,
            label=label,
            color=color,
            is_default=is_default,
            display_order=display_order,
            tenant_id=current_user.tenant_id
        )
        db.session.add(status)
        db.session.commit()

        flash('Status created successfully!', 'success')
        return redirect(url_for('list_statuses'))

    return render_template('statuses/form.html')


@app.route('/statuses/<int:status_id>/edit', methods=['GET', 'POST'])
@login_required
@tenant_required
@owner_required
def edit_status(status_id):
    """Edit status"""
    status = CIStatus.query.filter_by(
        id=status_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()

    if request.method == 'POST':
        status.name = request.form.get('name')
        status.label = request.form.get('label')
        status.color = request.form.get('color', 'info')
        status.is_default = request.form.get('is_default') == 'on'
        status.display_order = request.form.get('display_order', 0, type=int)

        # If this is default, unset others
        if status.is_default:
            CIStatus.query.filter_by(
                tenant_id=current_user.tenant_id,
                is_default=True
            ).update({'is_default': False})
            status.is_default = True

        db.session.commit()

        flash('Status updated successfully!', 'success')
        return redirect(url_for('list_statuses'))

    return render_template('statuses/form.html', status=status)


@app.route('/statuses/<int:status_id>/delete', methods=['POST'])
@login_required
@tenant_required
@owner_required
def delete_status(status_id):
    """Delete status"""
    status = CIStatus.query.filter_by(
        id=status_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()

    # Don't allow deleting if there are items with this status
    from app import ConfigItem
    items_count = ConfigItem.query.filter_by(
        tenant_id=current_user.tenant_id,
        status=status.name
    ).count()

    if items_count > 0:
        flash(f'Cannot delete status. {items_count} items have this status.', 'error')
        return redirect(url_for('list_statuses'))

    db.session.delete(status)
    db.session.commit()

    flash('Status deleted successfully!', 'success')
    return redirect(url_for('list_statuses'))


# ==================== Config Item Routes ====================

@app.route('/config-items')
@login_required
@tenant_required
def list_config_items():
    """List all config items for current tenant"""
    ci_type_filter = request.args.get('ci_type', type=int)
    status_filter = request.args.get('status')

    # Parse multiple field filters with operators (filter_field_0=1&filter_operator_0=contains&filter_value_0=xyz)
    field_filters = {}
    filter_idx = 0
    while True:
        field_id = request.args.get(f'filter_field_{filter_idx}')
        operator = request.args.get(f'filter_operator_{filter_idx}', 'contains')
        value = request.args.get(f'filter_value_{filter_idx}')
        
        if not field_id:
            # No more filters
            break
        
        if value:  # Only add if value is provided
            field_filters[f'field_{field_id}_{operator}'] = value
        
        filter_idx += 1

    query = ConfigItem.query.filter_by(tenant_id=current_user.tenant_id)

    if ci_type_filter:
        query = query.filter_by(ci_type_id=ci_type_filter)
    if status_filter:
        query = query.filter_by(status=status_filter)

    # Filter by multiple custom field values with operators
    if field_filters:
        for filter_key, field_value in field_filters.items():
            # Parse field_id and operator from key (e.g., field_1_contains -> field_id=1, operator=contains)
            parts = filter_key.split('_')
            if len(parts) >= 3:
                field_id = parts[1]
                operator = '_'.join(parts[2:])
                
                if operator == 'contains':
                    query = query.join(ConfigItem.field_values).filter(
                        CIFieldValue.field_id == field_id,
                        CIFieldValue.value_text.ilike(f'%{field_value}%')
                    )
                elif operator == 'not_contains':
                    query = query.join(ConfigItem.field_values).filter(
                        CIFieldValue.field_id == field_id,
                        ~CIFieldValue.value_text.ilike(f'%{field_value}%')
                    )
                elif operator == 'equals':
                    query = query.join(ConfigItem.field_values).filter(
                        CIFieldValue.field_id == field_id,
                        CIFieldValue.value_text == field_value
                    )
                elif operator == 'not_equals':
                    query = query.join(ConfigItem.field_values).filter(
                        CIFieldValue.field_id == field_id,
                        CIFieldValue.value_text != field_value
                    )
                elif operator == 'starts_with':
                    query = query.join(ConfigItem.field_values).filter(
                        CIFieldValue.field_id == field_id,
                        CIFieldValue.value_text.ilike(f'{field_value}%')
                    )
                elif operator == 'ends_with':
                    query = query.join(ConfigItem.field_values).filter(
                        CIFieldValue.field_id == field_id,
                        CIFieldValue.value_text.ilike(f'%{field_value}')
                    )

    config_items = query.order_by(ConfigItem.name).all()
    ci_types = CIType.query.filter_by(tenant_id=current_user.tenant_id).all()
    statuses = CIStatus.query.filter_by(tenant_id=current_user.tenant_id).order_by(CIStatus.display_order).all()

    # Get all fields for the selected CI type (or all fields if no type selected)
    fields_query = CITypeField.query.join(CIType).filter(CIType.tenant_id == current_user.tenant_id)
    if ci_type_filter:
        fields_query = fields_query.filter_by(ci_type_id=ci_type_filter)
    fields = fields_query.order_by(CITypeField.display_order).all()
    
    # Convert fields to JSON-serializable list
    fields_json = [{'id': f.id, 'label': f.label} for f in fields]

    return render_template('config_items/list.html',
                         config_items=config_items,
                         ci_types=ci_types,
                         statuses=statuses,
                         fields=fields,
                         fields_json=fields_json,
                         selected_ci_type=ci_type_filter,
                         selected_status=status_filter,
                         selected_field_filters=field_filters)


@app.route('/config-items/new', methods=['GET', 'POST'])
@login_required
@tenant_required
def create_config_item():
    """Create new config item"""
    ci_types = CIType.query.filter_by(tenant_id=current_user.tenant_id).all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        ci_type_id = request.form.get('ci_type_id', type=int)
        status = request.form.get('status', 'active')
        
        config_item = ConfigItem(
            name=name,
            description=description,
            ci_type_id=ci_type_id,
            tenant_id=current_user.tenant_id,
            status=status,
            created_by=current_user.id
        )
        db.session.add(config_item)
        db.session.flush()  # Get the ID
        
        # Get fields for this CI type and save values
        if ci_type_id:
            fields = CITypeField.query.filter_by(ci_type_id=ci_type_id).all()
            for field in fields:
                value = request.form.get(f'field_{field.id}')
                if value or field.is_required:
                    field_value = CIFieldValue(
                        ci_id=config_item.id,
                        field_id=field.id,
                        value_text=value or field.default_value or ''
                    )
                    db.session.add(field_value)
        
        db.session.commit()

        # Log creation in history
        history = CIHistory(
            ci_id=config_item.id,
            user_id=current_user.id,
            action='created',
            field_name='all',
            new_value=f'Name: {name}, Status: {status}, CI Type ID: {ci_type_id}',
            comment='Config Item created'
        )
        db.session.add(history)
        db.session.commit()

        flash('Config Item created successfully!', 'success')
        return redirect(url_for('list_config_items'))

    # Get ci_type_id from query param to pre-select
    selected_ci_type = request.args.get('ci_type', type=int)
    statuses = CIStatus.query.filter_by(tenant_id=current_user.tenant_id).order_by(CIStatus.display_order).all()

    # Build ci_types_with_fields for the template
    ci_types_with_fields = []
    for ci_type in ci_types:
        fields_data = []
        for field in ci_type.fields:
            fields_data.append({
                'id': field.id,
                'name': field.name,
                'label': field.label,
                'field_type': field.field_type,
                'is_required': field.is_required,
                'default_value': field.default_value or '',
                'options': field.options or '',
                'display_order': field.display_order or 0
            })
        ci_types_with_fields.append({
            'id': ci_type.id,
            'name': ci_type.name,
            'fields': fields_data
        })

    return render_template('config_items/form.html', 
                         ci_types=ci_types, 
                         ci_types_with_fields=ci_types_with_fields,
                         statuses=statuses,
                         selected_ci_type=selected_ci_type)


@app.route('/config-items/<int:ci_id>')
@login_required
@tenant_required
def view_config_item(ci_id):
    """View config item details"""
    config_item = ConfigItem.query.filter_by(
        id=ci_id, 
        tenant_id=current_user.tenant_id
    ).first_or_404()
    
    return render_template('config_items/view.html', config_item=config_item)


@app.route('/config-items/<int:ci_id>/edit', methods=['GET', 'POST'])
@login_required
@tenant_required
def edit_config_item(ci_id):
    """Edit config item"""
    config_item = ConfigItem.query.filter_by(
        id=ci_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()
    ci_types = CIType.query.filter_by(tenant_id=current_user.tenant_id).all()
    statuses = CIStatus.query.filter_by(tenant_id=current_user.tenant_id).order_by(CIStatus.display_order).all()

    # Build ci_types_with_fields for the template
    ci_types_with_fields = []
    for ci_type in ci_types:
        fields_data = []
        for field in ci_type.fields:
            fields_data.append({
                'id': field.id,
                'name': field.name,
                'label': field.label,
                'field_type': field.field_type,
                'is_required': field.is_required,
                'default_value': field.default_value or '',
                'options': field.options or '',
                'display_order': field.display_order or 0
            })
        ci_types_with_fields.append({
            'id': ci_type.id,
            'name': ci_type.name,
            'fields': fields_data
        })

    if request.method == 'POST':
        changes = []

        # Track field changes
        if config_item.name != request.form.get('name'):
            changes.append(('name', config_item.name, request.form.get('name')))
            config_item.name = request.form.get('name')

        if config_item.description != request.form.get('description'):
            changes.append(('description', config_item.description, request.form.get('description')))
            config_item.description = request.form.get('description')

        old_ci_type = config_item.ci_type_id
        if str(old_ci_type) != str(request.form.get('ci_type_id')):
            changes.append(('ci_type_id', old_ci_type, request.form.get('ci_type_id')))
            config_item.ci_type_id = request.form.get('ci_type_id')

        if config_item.status != request.form.get('status'):
            changes.append(('status', config_item.status, request.form.get('status')))
            config_item.status = request.form.get('status')

        db.session.commit()

        # Update custom field values
        fields = CITypeField.query.filter_by(ci_type_id=config_item.ci_type_id).all()
        for field in fields:
            new_value = request.form.get(f'field_{field.id}')
            existing_value = CIFieldValue.query.filter_by(ci_id=ci_id, field_id=field.id).first()
            
            if existing_value:
                if str(existing_value.value_text) != str(new_value):
                    changes.append((f'field:{field.label}', existing_value.value_text, new_value))
                    existing_value.value_text = new_value or field.default_value or ''
            elif new_value or field.is_required:
                changes.append((f'field:{field.label}', 'None', new_value))
                field_value = CIFieldValue(
                    ci_id=ci_id,
                    field_id=field.id,
                    value_text=new_value or field.default_value or ''
                )
                db.session.add(field_value)
        
        db.session.commit()

        # Log each change in history
        for field, old_val, new_val in changes:
            history = CIHistory(
                ci_id=config_item.id,
                user_id=current_user.id,
                action='updated' if not field.startswith('field:') and field != 'status' else 'status_changed' if field == 'status' else 'updated',
                field_name=field,
                old_value=str(old_val) if old_val else 'None',
                new_value=str(new_val) if new_val else 'None',
                comment=f'{field} changed'
            )
            db.session.add(history)
        db.session.commit()

        flash('Config Item updated successfully!', 'success')
        return redirect(url_for('view_config_item', ci_id=config_item.id))

    return render_template('config_items/form.html', 
                         config_item=config_item, 
                         ci_types=ci_types,
                         ci_types_with_fields=ci_types_with_fields,
                         statuses=statuses)


@app.route('/config-items/<int:ci_id>/delete', methods=['POST'])
@login_required
@tenant_required
def delete_config_item(ci_id):
    """Delete config item"""
    config_item = ConfigItem.query.filter_by(
        id=ci_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()

    # Log deletion in history before deleting
    history = CIHistory(
        ci_id=config_item.id,
        user_id=current_user.id,
        action='deleted',
        field_name='all',
        old_value=f'Name: {config_item.name}, Status: {config_item.status}',
        comment='Config Item deleted'
    )
    db.session.add(history)
    
    db.session.delete(config_item)
    db.session.commit()

    flash('Config Item deleted successfully!', 'success')
    return redirect(url_for('list_config_items'))


@app.route('/config-items/<int:ci_id>/history')
@login_required
@tenant_required
def view_config_item_history(ci_id):
    """View config item history"""
    config_item = ConfigItem.query.filter_by(
        id=ci_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()

    # Get filter parameters
    action_filter = request.args.get('action')
    field_filter = request.args.get('field')
    user_filter = request.args.get('user', type=int)

    # Build query
    query = CIHistory.query.filter_by(ci_id=ci_id)
    
    if action_filter:
        query = query.filter_by(action=action_filter)
    if field_filter:
        query = query.filter(CIHistory.field_name.ilike(f'%{field_filter}%'))
    if user_filter:
        query = query.filter_by(user_id=user_filter)

    history = query.order_by(CIHistory.created_at.desc()).all()
    
    # Get unique users who made changes
    users = User.query.filter(
        User.id.in_(db.session.query(db.func.distinct(CIHistory.user_id)).filter_by(ci_id=ci_id))
    ).all()

    return render_template('config_items/history.html', 
                         config_item=config_item, 
                         history=history,
                         users=users,
                         selected_action=action_filter,
                         selected_field=field_filter,
                         selected_user=user_filter)


# ==================== Relationships Routes ====================

@app.route('/config-items/<int:ci_id>/relationships', methods=['GET', 'POST'])
@login_required
@tenant_required
def manage_relationships(ci_id):
    """Manage relationships for a config item"""
    config_item = ConfigItem.query.filter_by(
        id=ci_id, 
        tenant_id=current_user.tenant_id
    ).first_or_404()
    
    if request.method == 'POST':
        target_ci_id = request.form.get('target_ci_id')
        relationship_type = request.form.get('relationship_type')
        description = request.form.get('description')
        
        relationship = CIRelationship(
            source_ci_id=config_item.id,
            target_ci_id=target_ci_id,
            relationship_type=relationship_type,
            description=description
        )
        db.session.add(relationship)
        db.session.commit()
        
        flash('Relationship created successfully!', 'success')
        return redirect(url_for('manage_relationships', ci_id=ci_id))
    
    # Get all CIs except current one
    all_cis = ConfigItem.query.filter(
        ConfigItem.tenant_id == current_user.tenant_id,
        ConfigItem.id != config_item.id
    ).all()
    
    # Get existing relationships
    outgoing = CIRelationship.query.filter_by(source_ci_id=ci_id).all()
    incoming = CIRelationship.query.filter_by(target_ci_id=ci_id).all()
    
    return render_template('config_items/relationships.html', 
                         config_item=config_item,
                         all_cis=all_cis,
                         outgoing=outgoing,
                         incoming=incoming)


@app.route('/relationships/<int:rel_id>/delete', methods=['POST'])
@login_required
@tenant_required
def delete_relationship(rel_id):
    """Delete a relationship"""
    relationship = CIRelationship.query.get_or_404(rel_id)
    config_item = ConfigItem.query.filter_by(
        id=relationship.source_ci_id,
        tenant_id=current_user.tenant_id
    ).first_or_404()
    
    db.session.delete(relationship)
    db.session.commit()
    
    flash('Relationship deleted successfully!', 'success')
    return redirect(url_for('manage_relationships', ci_id=config_item.id))


# ==================== Admin Routes ====================

@app.route('/admin/users')
@login_required
def admin_users():
    """Admin: List all users in tenant"""
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))
    
    users = User.query.filter_by(tenant_id=current_user.tenant_id).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users/new', methods=['GET', 'POST'])
@login_required
def admin_create_user():
    """Admin: Create new user"""
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        is_owner = request.form.get('is_owner') == 'on'

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('admin/user_form.html')

        user = User(
            username=username,
            email=email,
            tenant_id=current_user.tenant_id,
            is_admin=is_admin,
            is_owner=is_owner
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('User created successfully!', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin/user_form.html')


@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    """Admin: Edit existing user"""
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))

    user = User.query.filter_by(id=user_id, tenant_id=current_user.tenant_id).first_or_404()

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        is_owner = request.form.get('is_owner') == 'on'

        # Check for duplicate username (excluding current user)
        existing = User.query.filter_by(username=username).first()
        if existing and existing.id != user.id:
            flash('Username already exists.', 'error')
            return render_template('admin/user_edit.html', user=user)

        # Check for duplicate email (excluding current user)
        existing_email = User.query.filter_by(email=email).first()
        if existing_email and existing_email.id != user.id:
            flash('Email already registered.', 'error')
            return render_template('admin/user_edit.html', user=user)

        user.username = username
        user.email = email
        if password:  # Only update password if provided
            user.set_password(password)
        user.is_admin = is_admin
        user.is_owner = is_owner
        db.session.commit()

        flash('User updated successfully!', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin/user_edit.html', user=user)


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    """Admin: Delete user"""
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))

    user = User.query.filter_by(id=user_id, tenant_id=current_user.tenant_id).first_or_404()

    # Prevent self-deletion
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_users'))

    db.session.delete(user)
    db.session.commit()

    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_users'))


# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500


# ==================== Database Initialization ====================

def init_db():
    """Initialize the database"""
    with app.app_context():
        db.create_all()
        print('Database initialized successfully!')


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
