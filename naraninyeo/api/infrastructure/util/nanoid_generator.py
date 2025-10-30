import nanoid

class NanoidGenerator:
    def generate_id(self) -> str:
        return nanoid.generate()
