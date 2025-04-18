from flask import Flask, request, jsonify
from flask_cors import CORS
from extensions import db
from models import User, Event
from werkzeug.security import generate_password_hash
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import uuid

app = Flask(__name__)
CORS(app)

# Config MySQL (usa i tuoi valori reali)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:password@localhost/events_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db.init_app(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

with app.app_context():
    db.create_all()
    if not User.query.first():
        admin = User(username="admin", password="admin123")
        db.session.add(admin)
        db.session.commit()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"success": False, "message": "Dati mancanti"}), 400

    user = User.query.filter_by(username=data['username']).first()
    if user and user.check_password(data['password']):
        user.last_login = datetime.utcnow()
        db.session.commit()
        return jsonify({"success": True, "user": user.get_dict()}), 200

    return jsonify({"success": False, "message": "Credenziali non valide"}), 401

@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.get_dict() for user in users]), 200

@app.route('/events', methods=['GET', 'POST'])
def handle_events():
    if request.method == 'GET':
        events = Event.query.order_by(Event.date).all()
        return jsonify([e.get_dict() for e in events]), 200
    elif request.method == 'POST':
        data = request.get_json()
        try:
            creator = User.query.get(data.get('created_by', 1))
            if not creator:
                return jsonify({'success': False, 'message': 'Utente non valido'}), 400

            new_event = Event(
                title=data['title'],
                content=data['content'],
                date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
                created_by=creator.id,
                updated_by=creator.id,
                location=data.get('location', ''),
                tags=','.join(data.get('tags', [])),
                is_important=data.get('is_important', False),
                images=data.get('images', '')
            )
            db.session.add(new_event)
            db.session.commit()
            return jsonify({'success': True, 'event': new_event.get_dict()}), 201
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/events/<int:event_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_single_event(event_id):
    event = Event.query.get_or_404(event_id)
    if request.method == 'GET':
        return jsonify(event.get_dict(include_content=True)), 200
    elif request.method == 'PUT':
        data = request.get_json()
        try:
            updater = User.query.get(data.get('updated_by', 1))
            if not updater:
                return jsonify({'success': False, 'message': 'Utente non valido'}), 400

            update_data = {
                'title': data.get('title', event.title),
                'content': data.get('content', event.content),
                'location': data.get('location', event.location),
                'tags': ','.join(data.get('tags', event.tags.split(','))) if 'tags' in data else event.tags,
                'is_important': data.get('is_important', event.is_important),
                'images': data.get('images', event.images),
                'updated_by': updater.id
            }
            if 'date' in data:
                update_data['date'] = datetime.strptime(data['date'], '%Y-%m-%d').date()

            event.update(update_data, updater.id)
            db.session.commit()
            return jsonify({'success': True, 'event': event.get_dict()}), 200
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
    elif request.method == 'DELETE':
        try:
            if event.images:
                for image_path in event.images.split(','):
                    if os.path.exists(image_path):
                        os.remove(image_path)
            db.session.delete(event)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Evento eliminato'}), 200
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/events', methods=['POST'])
def create_event_with_images():
    try:
        data = request.form
        images = request.files.getlist('images')
        creator = User.query.get(int(data.get('created_by', 1)))
        if not creator:
            return jsonify({'success': False, 'message': 'Utente non valido'}), 400

        image_paths = []
        for image in images:
            if image and allowed_file(image.filename):
                filename = f"{uuid.uuid4().hex}_{secure_filename(image.filename)}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(save_path)
                image_paths.append(f"{UPLOAD_FOLDER}/{filename}")

        new_event = Event(
            title=data['title'],
            content=data['content'],
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            created_by=creator.id,
            updated_by=creator.id,
            location=data.get('location', ''),
            tags=data.get('tags', ''),
            is_important=data.get('is_important', 'false') == 'true',
            images=','.join(image_paths)
        )
        db.session.add(new_event)
        db.session.commit()
        return jsonify({'success': True, 'event': new_event.get_dict()}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/upload-image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'Nessun file'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'File vuoto'}), 400
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(save_path)
            return jsonify({'success': True, 'imageUrl': f"/{UPLOAD_FOLDER}/{unique_filename}"}), 200
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False, 'message': 'Formato non valido'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4200)
