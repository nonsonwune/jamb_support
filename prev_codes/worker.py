# worker.py
import json
import pika
from pika.exceptions import AMQPConnectionError
import asyncio
from config import (
    RABBITMQ_HOST,
    RABBITMQ_PORT,
    RABBITMQ_VHOST,
    RABBITMQ_USERNAME,
    RABBITMQ_PASSWORD,
)
from logger import worker_logger as logger
from gemini_processor import gemini_processor


async def connect_to_rabbitmq():
    retry_count = 0
    while True:
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    virtual_host=RABBITMQ_VHOST,
                    credentials=credentials,
                    socket_timeout=5,
                )
            )
            channel = connection.channel()
            channel.queue_declare(queue="ticket_queue", durable=True)
            logger.info("Worker successfully connected to RabbitMQ")
            return connection, channel
        except AMQPConnectionError as e:
            retry_count += 1
            logger.error(
                f"Worker failed to connect to RabbitMQ (attempt {retry_count}): {str(e)}"
            )
            if retry_count >= 5:
                logger.error("Max retries reached. Exiting worker.")
                raise
            await asyncio.sleep(5)


async def process_ticket(ticket):
    try:
        processed_ticket = await gemini_processor.process_tickets_batch([ticket])
        return processed_ticket[0]
    except Exception as e:
        logger.error(
            f"Error processing ticket {ticket.get('ticket_id', 'Unknown')}: {str(e)}"
        )
        return ticket


def callback(ch, method, properties, body):
    ticket = json.loads(body)
    asyncio.run(process_ticket(ticket))
    ch.basic_ack(delivery_tag=method.delivery_tag)


async def main():
    connection, channel = await connect_to_rabbitmq()

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="ticket_queue", on_message_callback=callback)

    logger.info("Worker waiting for messages. To exit press CTRL+C")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    asyncio.run(main())
