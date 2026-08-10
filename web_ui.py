from flask import Flask, render_template, request, jsonify
import pika
import json
import uuid
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = "/data"
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx', 'jpg', 'png'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# RabbitMQ Configuration (from env vars)
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "default_user_s3iaVDl5FXuzPZBBFMf")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "dNcEF8vLNBF3q_SSkx_yoZ7GGU7FWylW")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "test_queue")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def produce_message(doc_id, original_filename, file_path):
    """Send message to RabbitMQ"""
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=credentials,
            connection_attempts=3,
            retry_delay=2
        )

        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

        message = {
            "doc_id": doc_id,
            "original_filename": original_filename,
            "file_path": file_path,
            "uploaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }

        channel.basic_publish(
            exchange='',
            routing_key=RABBITMQ_QUEUE,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
            )
        )

        connection.close()
        return True, message
    except Exception as e:
        return False, str(e)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload"""
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file part'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

        # Generate doc_id
        doc_id = str(uuid.uuid4())

        # Save file
        original_filename = secure_filename(file.filename)
        filename = f"{doc_id}_{original_filename}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        # Produce message
        success, result = produce_message(doc_id, original_filename, file_path)

        if success:
            return jsonify({
                'success': True,
                'message': 'File uploaded and message produced successfully!',
                'data': result
            }), 200
        else:
            # Clean up file if message production failed
            os.remove(file_path)
            return jsonify({'success': False, 'error': f'Failed to produce message: {result}'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
