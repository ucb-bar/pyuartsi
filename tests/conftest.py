from dataclasses import dataclass, field


@dataclass
class FakeTransport:
    incoming: bytearray = field(default_factory=bytearray)
    writes: list[bytes] = field(default_factory=list)
    close_count: int = 0

    def read_exact(self, size: int) -> bytes:
        if len(self.incoming) < size:
            raise AssertionError(f"test queued {len(self.incoming)} of {size} bytes")
        data = bytes(self.incoming[:size])
        del self.incoming[:size]
        return data

    def write_all(self, data: bytes) -> None:
        self.writes.append(data)

    def close(self) -> None:
        self.close_count += 1
