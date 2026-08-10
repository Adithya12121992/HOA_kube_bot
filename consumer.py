import pika
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# RabbitMQ Configuration (from env vars)
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "default_user_jKPj7zmhwSN3JMMb5um")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "_hiL6pXPY7ITdQKs9gxS_uw7HqNiBFj7")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "test_queue")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))

# Concurrency settings
MAX_CONCURRENT_MESSAGES = 3
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_MESSAGES)
channel_lock = threading.Lock()  # Thread-safe channel operations


def process_message(message_data, delivery_tag, channel):
    """Process a single message (called in thread pool)"""
    try:
        print(f"\n⏳ [Thread-{threading.current_thread().name}] Processing message {delivery_tag}:")
        print(json.dumps(message_data, indent=2))

        file_path = message_data.get('file_path')
        filename = message_data.get('original_filename', 'unknown')

        # PLACEHOLDER: Add your processing logic here
        print(f"[TODO] Processing logic for: {filename}")

        # Simulate processing time (replace with actual processing)
        # time.sleep(2)

        # Delete file from PVC after processing
        if file_path:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"🗑️  Deleted file: {file_path}")
                else:
                    print(f"⚠️  File not found: {file_path}")
            except Exception as e:
                print(f"⚠️  Error deleting file {file_path}: {e}")

        # Mark message as processed (acknowledge it) - thread-safe
        with channel_lock:
            channel.basic_ack(delivery_tag=delivery_tag)
        print(f"✓ [Thread-{threading.current_thread().name}] Message {delivery_tag} processed successfully")

    except Exception as e:
        print(f"✗ [Thread-{threading.current_thread().name}] Error processing message {delivery_tag}: {e}")
        # Reject message (it will be requeued) - thread-safe
        with channel_lock:
            channel.basic_nack(delivery_tag=delivery_tag, requeue=True)


def get_queue_message_count():
    """Get the number of messages in the queue (without consuming them)"""
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

        # Declare queue as passive=True (don't create, just check)
        method = channel.queue_declare(queue=RABBITMQ_QUEUE, passive=True)
        message_count = method.method.message_count

        connection.close()
        return message_count
    except Exception as e:
        print(f"Error getting queue count: {e}")
        import traceback
        traceback.print_exc()
        return None


def consume_messages():
    """Consume messages with concurrent processing (max 3 at a time)"""
    reconnect_attempts = 0
    max_reconnect_attempts = 5

    while reconnect_attempts < max_reconnect_attempts:
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                connection_attempts=3,
                retry_delay=2,
                blocked_connection_timeout=300
            )

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            # Declare queue
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

            # Set prefetch_count to MAX_CONCURRENT_MESSAGES
            channel.basic_qos(prefetch_count=MAX_CONCURRENT_MESSAGES)

            def callback(ch, method, properties, body):
                """Handle incoming message - process concurrently"""
                try:
                    message = json.loads(body)
                    print(f"\n📨 Message {method.delivery_tag} received, queued for processing")

                    # Submit to thread pool for concurrent processing
                    executor.submit(process_message, message, method.delivery_tag, ch)

                except Exception as e:
                    print(f"Error queuing message: {e}")
                    with channel_lock:
                        try:
                            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        except:
                            pass

            # Consume with auto_ack=False
            channel.basic_consume(
                queue=RABBITMQ_QUEUE,
                on_message_callback=callback,
                auto_ack=False
            )

            print(f"🎧 Concurrent Consumer Active")
            print(f"📊 Queue: '{RABBITMQ_QUEUE}'")
            print(f"⚙️  Max concurrent messages: {MAX_CONCURRENT_MESSAGES}")
            print("Press Ctrl+C to stop\n")

            reconnect_attempts = 0  # Reset on successful connection
            channel.start_consuming()

        except KeyboardInterrupt:
            print("\n✓ Consumer stopped")
            executor.shutdown(wait=True)
            break
        except pika.exceptions.StreamLostError as e:
            reconnect_attempts += 1
            print(f"\n⚠️  Stream lost, reconnecting... (Attempt {reconnect_attempts}/{max_reconnect_attempts})")
            time.sleep(2)
        except Exception as e:
            reconnect_attempts += 1
            print(f"\n✗ Error: {e}")
            if reconnect_attempts < max_reconnect_attempts:
                print(f"Retrying... (Attempt {reconnect_attempts}/{max_reconnect_attempts})")
                time.sleep(2)
            else:
                import traceback
                traceback.print_exc()
                break


if __name__ == "__main__":
    print(f"Connecting to RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}")
    print(f"Using credentials: {RABBITMQ_USER}:***\n")

    # Check queue message count
    count = get_queue_message_count()
    if count is not None:
        print(f"📊 Current messages in queue '{RABBITMQ_QUEUE}': {count}\n")

    # Start consuming
    consume_messages()
