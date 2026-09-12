import base64
import hashlib
import os
from typing import Union

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


BytesLike = Union[str, bytes]


class AESer:
    """AES-CBC encrypt/decrypt helper.

    encrypt() returns a base64 string that contains iv + ciphertext.
    decrypt() accepts that base64 string and returns the original text.
    """

    block_size = 128
    iv_size = 16

    def __init__(self, key: BytesLike, encoding: str = "utf-8"):
        self.encoding = encoding
        self.key = self._normalize_key(key)

    def encrypt(self, plaintext: BytesLike) -> str:
        plaintext_bytes = self._to_bytes(plaintext)
        iv = os.urandom(self.iv_size)

        padder = padding.PKCS7(self.block_size).padder()
        padded_data = padder.update(plaintext_bytes) + padder.finalize()

        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        return base64.b64encode(iv + ciphertext).decode(self.encoding)

    def decrypt(self, token: BytesLike) -> str:
        encrypted_data = base64.b64decode(self._to_bytes(token))
        iv = encrypted_data[:self.iv_size]
        ciphertext = encrypted_data[self.iv_size:]

        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = padding.PKCS7(self.block_size).unpadder()
        plaintext = unpadder.update(padded_data) + unpadder.finalize()

        return plaintext.decode(self.encoding)

    def _to_bytes(self, value: BytesLike) -> bytes:
        if isinstance(value, bytes):
            return value
        return str(value).encode(self.encoding)

    def _normalize_key(self, key: BytesLike) -> bytes:
        key_bytes = self._to_bytes(key)
        if len(key_bytes) in (16, 24, 32):
            return key_bytes
        return hashlib.sha256(key_bytes).digest()


if __name__ == "__main__":
    aes = AESer("1234567890abcdef")
    encrypted_text = aes.encrypt("hello django")
    decrypted_text = aes.decrypt(encrypted_text)
    print(encrypted_text)
    print(decrypted_text)
