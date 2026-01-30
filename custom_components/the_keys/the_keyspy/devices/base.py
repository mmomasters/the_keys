class TheKeysDevice:
    def __init__(self, id: int) -> None:
        self._id = id

    @property
    def id(self) -> int:
        return self._id
