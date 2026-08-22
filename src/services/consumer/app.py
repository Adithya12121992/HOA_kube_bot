import pika
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.config.settings import (
    RABBITMQ_HOST,
    RABBITMQ_PORT,
    RABBITMQ_USER,
    RABBITMQ_PASSWORD,
    RABBITMQ_QUEUE,
    CHUNKS_JSON_PATH,
)
from src.rag.extract import extract_document
from src.rag.chunk import chunk_document, classify_doc_type
from src.rag.status import write_status
from src.rag.summarize import summarize_document
import src.rag.store as store

# Concurrency settings
MAX_CONCURRENT_MESSAGES = 3
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_MESSAGES)
channel_lock = threading.Lock()  # Thread-safe channel operations
chunks_json_lock = threading.Lock()  # Thread-safe chunks.json append

# Embed+store in batches so status.chunks_done reflects real progress
# instead of jumping straight from 0 to chunks_total.
EMBED_BATCH_SIZE = 16


def _append_chunks_json(chunks: list[dict]) -> None:
    """Append chunk records (no embeddings) to the debug/audit chunks.json.

    Thread-safe: multiple documents can be processed concurrently
    (MAX_CONCURRENT_MESSAGES), and this file is shared across all of them.
    """
    path = Path(CHUNKS_JSON_PATH)
    with chunks_json_lock:
        existing = []
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                existing = []
        existing.extend(chunks)
        path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


def process_message(message_data, delivery_tag, channel):
    """Process a single uploaded document: extract -> chunk -> embed -> store -> summarize."""
    thread_name = threading.current_thread().name
    doc_id = message_data.get("doc_id")
    file_path = message_data.get("file_path")
    filename = message_data.get("original_filename", "unknown")

    print(f"\n⏳ [Thread-{thread_name}] Processing message {delivery_tag}: {filename}")

    try:
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        write_status(doc_id, filename, stage="extracting")
        doc = extract_document(Path(file_path), strip_boilerplate=True)
        print(f"  [Thread-{thread_name}] Extracted {doc['total_pages']} pages")

        write_status(doc_id, filename, stage="chunking")
        doc_type = classify_doc_type(filename)
        is_ccrs = "CC&Rs" in filename
        chunks = chunk_document(filename, doc["full_text"], doc["page_offsets"], is_ccrs=is_ccrs)
        print(f"  [Thread-{thread_name}] Produced {len(chunks)} chunks (doc_type={doc_type})")

        write_status(
            doc_id, filename, stage="embedding",
            doc_type=doc_type, chunks_total=len(chunks), chunks_done=0,
        )
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            store.add_chunks(batch)
            chunks_done = min(i + EMBED_BATCH_SIZE, len(chunks))
            write_status(doc_id, filename, stage="embedding", chunks_done=chunks_done)
            print(f"  [Thread-{thread_name}] Embedded {chunks_done}/{len(chunks)} chunks")

        _append_chunks_json(chunks)

        write_status(doc_id, filename, stage="summarizing")
        summary = summarize_document(doc_type, doc["full_text"])
        if summary:
            print(f"  [Thread-{thread_name}] Summary: {summary}")
        else:
            print(f"  [Thread-{thread_name}] Summary skipped (no LLM reachable)")

        write_status(doc_id, filename, stage="ready", summary=summary)

        # Delete file from PVC after successful processing
        try:
            os.remove(file_path)
            print(f"  🗑️  [Thread-{thread_name}] Deleted file: {file_path}")
        except OSError as e:
            print(f"  ⚠️  [Thread-{thread_name}] Error deleting file {file_path}: {e}")

        with channel_lock:
            channel.basic_ack(delivery_tag=delivery_tag)
        print(f"✓ [Thread-{thread_name}] Message {delivery_tag} processed successfully — {filename} is ready")

    except Exception as e:
        print(f"✗ [Thread-{thread_name}] Error processing message {delivery_tag}: {e}")
        if doc_id:
            write_status(doc_id, filename, stage="error", error_message=str(e))
        with channel_lock:
            # requeue=False: a processing failure (bad PDF, corrupt file, etc)
            # is not transient - requeuing would just loop forever reprocessing
            # the same broken message. Transient issues (connection loss) are
            # handled separately by consume_messages()'s reconnect logic, not
            # by nacking individual messages.
            channel.basic_nack(delivery_tag=delivery_tag, requeue=False)


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
