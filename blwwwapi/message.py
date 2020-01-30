from dataclasses import dataclass, field

@dataclass(frozen=True)
class Message:
  sender: str
  payload: dict = field(default_factory=dict)
