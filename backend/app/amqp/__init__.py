"""Private RabbitMQ transport for API business rules and Web delivery."""
from .consumer import ApiAmqpConsumer

__all__ = ['ApiAmqpConsumer']
