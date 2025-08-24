from abc import ABC, abstractmethod
from typing import AsyncIterator

from naraninyeo.domain.model.message import Message
from naraninyeo.domain.model.reply import ReplyContext


class ReplyGenerator(ABC):
    @abstractmethod
    def generate_reply(self, context: ReplyContext) -> AsyncIterator[Message]: ...
