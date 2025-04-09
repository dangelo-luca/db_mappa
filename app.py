from flask import Flask, request, jsonify
from flask_cors import CORS
from extensions import db
from models import User, Event
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import uuid

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

CORS(app, resources={r"/*": {"origins": "https://4200-dangeloluca-provamappa-03tvdzd4899.ws-eu118.gitpod.io"}})

# Crea la cartella se non esiste
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

CORS(app, resources={r"/*": {"origins": "*"}})  # Consenti tutte le origini

# Configurazione del database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///events.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Creazione database e utente demo
with app.app_context():
    db.create_all()
    if not User.query.first():
        admin = User(username="admin", password="admin123")
        db.session.add(admin)
        db.session.commit()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    # Validazione base
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"success": False, "message": "Dati mancanti"}), 400

    user = User.query.filter_by(username=data['username']).first()
    
    if user and user.check_password(data['password']):
        # Aggiorna last_login
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Login riuscito",
            "user": user.get_dict()
        }), 200
    
    return jsonify({
        "success": False,
        "message": "Credenziali non valide"
    }), 401

@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.get_dict() for user in users]), 200

# Endpoint per la gestione degli eventi
@app.route('/events', methods=['GET', 'POST'])
def handle_events():
    print("Richiesta GET a /events ricevuta")
    if request.method == 'GET':
        events = Event.query.order_by(Event.date).all()
        print(f"Eventi recuperati dal database: {events}")
        event_dicts = [event.get_dict() for event in events]
        print(f"Eventi serializzati in JSON: {event_dicts}")
        return jsonify(event_dicts), 200
    # ... (codice POST)
    elif request.method == 'POST':
        # Crea un nuovo evento
        data = request.get_json()
        
        try:
            # Verifica che l'utente esista
            creator = User.query.get(data.get('created_by', 1))  # Default a admin (id=1)
            if not creator:
                return jsonify({
                    'success': False,
                    'message': 'Utente creatore non valido'
                }), 400
                
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
            
            return jsonify({
                'success': True,
                'message': 'Evento creato con successo',
                'event': new_event.get_dict()
            }), 201
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Errore nella creazione dell\'evento: {str(e)}'
            }), 400

@app.route('/events/<int:event_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_single_event(event_id):
    event = Event.query.get_or_404(event_id)
    
    if request.method == 'GET':
        return jsonify(event.get_dict(include_content=True)), 200
    
    elif request.method == 'PUT':
        data = request.get_json()
        
        try:
            # Verifica che l'utente che modifica esista
            updater = User.query.get(data.get('updated_by', 1))  # Default a admin (id=1)
            if not updater:
                return jsonify({
                    'success': False,
                    'message': 'Utente non valido'
                }), 400
                
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
                
            event.update(update_data)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Evento aggiornato con successo',
                'event': event.get_dict()
            }), 200
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Errore nell\'aggiornamento dell\'evento: {str(e)}'
            }), 400
    
    elif request.method == 'DELETE':
        try:
            # Prima elimina le immagini associate
            if event.images:
                for image_path in event.images.split(','):
                    if os.path.exists(image_path):
                        os.remove(image_path)
            
            db.session.delete(event)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Evento eliminato con successo'
            }), 200
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Errore nell\'eliminazione dell\'evento: {str(e)}'
            }), 400

@app.route('/api/events', methods=['POST'])
def create_event_with_images():
    try:
        data = request.form
        images = request.files.getlist('images')
        
        # Verifica che l'utente esista
        creator = User.query.get(int(data.get('created_by', 1)))  # Default a admin (id=1)
        if not creator:
            return jsonify({
                'success': False,
                'message': 'Utente creatore non valido'
            }), 400

        image_paths = []
        
        # Elabora tutte le immagini caricate
        for image in images:
            if image and allowed_file(image.filename):
                # Genera un nome unico per il file
                filename = f"{uuid.uuid4().hex}_{secure_filename(image.filename)}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(save_path)
                image_paths.append(f"{UPLOAD_FOLDER}/{filename}")

        # Crea un nuovo evento
        new_event = Event(
            title=data['title'],
            content=data['content'],
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            created_by=creator.id,
            updated_by=creator.id,
            location=data.get('location', ''),
            tags=data.get('tags', ''),
            is_important=data.get('is_important', 'false') == 'true',
            images=','.join(image_paths) if image_paths else None
        )
        
        db.session.add(new_event)
        db.session.commit()

        return jsonify({
            'success': True, 
            'message': 'Evento creato con successo!',
            'event': new_event.get_dict()
        }), 201

    except Exception as e:
        # Log dell'errore per debug
        print(f"Errore durante la creazione dell'evento: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Errore: {str(e)}'
        }), 500

@app.route('/upload-image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'Nessun file caricato'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Nessun file selezionato'}), 400
    
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(save_path)
            
            return jsonify({
                'success': True,
                'imageUrl': f"/{UPLOAD_FOLDER}/{unique_filename}"
            }), 200
        except Exception as e:
            return jsonify({'success': False, 'message': f'Errore durante il caricamento: {str(e)}'}), 500
    
    return jsonify({'success': False, 'message': 'Tipo file non consentito'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)