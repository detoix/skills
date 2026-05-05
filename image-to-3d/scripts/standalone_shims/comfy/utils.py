class ProgressBar:
    def __init__(self, total: int = 0):
        self.total = total
        self.current = 0

    def update(self, step: int = 1) -> None:
        self.current += step
