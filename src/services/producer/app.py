"""
Test Producer - Generates sample messages for RabbitMQ
(For testing/development only - can be disabled in production)
"""

import pika
import json
import uuid
from datetime import datetime, timezone

# TODO: Configure from environment/config
RABBITMQ_HOST = "hoa-rabbitmq"
RABBITMQ_PORT = 5672
RABBITMQ_QUEUE = "test_queue"


def produce_test_messages(count: int = 5):
    """Generate sample messages for testing"""
    try:
        credentials = pika.PlainCredentials("user", "bitnami")
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

        for i in range(count):
            message = {
                "doc_id": str(uuid.uuid4()),
                "original_filename": f"test_document_{i}.pdf",
                "file_path": f"/data/test_document_{i}.pdf",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }

            channel.basic_publish(
                exchange="",
                routing_key=RABBITMQ_QUEUE,
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2),
            )
            print(f"✓ Message {i+1} produced")

        connection.close()
        print(f"✓ {count} test messages produced")

    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    produce_test_messages(5)
