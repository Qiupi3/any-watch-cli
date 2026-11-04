from __future__ import annotations

"""Minimal AES-256-GCM decryption (no external dependencies).

Some players (for example Nontongo's ``px.js``) encrypt their configuration
with WebCrypto's AES-256-GCM.  Python's standard library has no AES, so this
module implements only the forward cipher and GCM authentication needed to
decrypt those payloads.  It is not intended as a general-purpose crypto
library.
"""

import hmac
from typing import Iterable


def _gf_mul(a: int, b: int) -> int:
    """Multiply two bytes in GF(2^8) modulo x^8 + x^4 + x^3 + x + 1."""
    product = 0
    for _ in range(8):
        if b & 1:
            product ^= a
        carry = a & 0x80
        a = (a << 1) & 0xFF
        if carry:
            a ^= 0x1B
        b >>= 1
    return product


def _rotl8(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (8 - shift))) & 0xFF


def _build_sbox() -> bytes:
    inverse = [0] * 256
    for value in range(1, 256):
        for candidate in range(1, 256):
            if _gf_mul(value, candidate) == 1:
                inverse[value] = candidate
                break
    sbox = bytearray(256)
    for value in range(256):
        inv = inverse[value]
        sbox[value] = (
            inv
            ^ _rotl8(inv, 1)
            ^ _rotl8(inv, 2)
            ^ _rotl8(inv, 3)
            ^ _rotl8(inv, 4)
            ^ 0x63
        )
    return bytes(sbox)


_SBOX = _build_sbox()


def _expand_key(key: bytes) -> tuple[list[list[int]], int]:
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24, or 32 bytes")
    nk = len(key) // 4
    rounds = nk + 6
    words = [list(key[index * 4 : index * 4 + 4]) for index in range(nk)]
    rcon = 1

    for index in range(nk, 4 * (rounds + 1)):
        temp = list(words[index - 1])
        if index % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[byte] for byte in temp]
            temp[0] ^= rcon
            rcon = _gf_mul(rcon, 2)
        elif nk > 6 and index % nk == 4:
            temp = [_SBOX[byte] for byte in temp]
        words.append([words[index - nk][pos] ^ temp[pos] for pos in range(4)])

    return words, rounds


def _shift_rows(state: list[int]) -> list[int]:
    return [
        state[0],
        state[5],
        state[10],
        state[15],
        state[4],
        state[9],
        state[14],
        state[3],
        state[8],
        state[13],
        state[2],
        state[7],
        state[12],
        state[1],
        state[6],
        state[11],
    ]


def _mix_columns(state: list[int]) -> list[int]:
    mixed: list[int] = []
    for column in range(4):
        a0, a1, a2, a3 = state[column * 4 : column * 4 + 4]
        mixed.extend(
            [
                _gf_mul(a0, 2) ^ _gf_mul(a1, 3) ^ a2 ^ a3,
                a0 ^ _gf_mul(a1, 2) ^ _gf_mul(a2, 3) ^ a3,
                a0 ^ a1 ^ _gf_mul(a2, 2) ^ _gf_mul(a3, 3),
                _gf_mul(a0, 3) ^ a1 ^ a2 ^ _gf_mul(a3, 2),
            ]
        )
    return mixed


class _AES:
    def __init__(self, key: bytes) -> None:
        words, self.rounds = _expand_key(key)
        self.round_keys = [
            [byte for word in words[index * 4 : index * 4 + 4] for byte in word]
            for index in range(self.rounds + 1)
        ]

    def encrypt_block(self, block: bytes) -> bytes:
        if len(block) != 16:
            raise ValueError("AES block must be 16 bytes")
        state = [byte ^ key for byte, key in zip(block, self.round_keys[0])]

        for round_index in range(1, self.rounds):
            state = [_SBOX[byte] for byte in state]
            state = _shift_rows(state)
            state = _mix_columns(state)
            state = [
                byte ^ key
                for byte, key in zip(state, self.round_keys[round_index])
            ]

        state = [_SBOX[byte] for byte in state]
        state = _shift_rows(state)
        return bytes(
            byte ^ key for byte, key in zip(state, self.round_keys[self.rounds])
        )


def _pad16(data: bytes) -> bytes:
    remainder = len(data) % 16
    if not remainder:
        return data
    return data + b"\x00" * (16 - remainder)


def _gfmul128(x: int, y: int) -> int:
    """Multiply two 128-bit blocks in GCM's GF(2^128)."""
    result = 0
    value = y
    for bit in range(127, -1, -1):
        if (x >> bit) & 1:
            result ^= value
        if value & 1:
            value = (value >> 1) ^ 0xE1000000000000000000000000000000
        else:
            value >>= 1
    return result


def _ghash(h: int, data: bytes) -> int:
    value = 0
    for offset in range(0, len(data), 16):
        block = data[offset : offset + 16]
        if len(block) < 16:
            block = block + b"\x00" * (16 - len(block))
        value = _gfmul128(value ^ int.from_bytes(block, "big"), h)
    return value


def _j0(aes: _AES, nonce: bytes) -> bytes:
    if len(nonce) == 12:
        return nonce + b"\x00\x00\x00\x01"
    h = int.from_bytes(aes.encrypt_block(b"\x00" * 16), "big")
    length = (len(nonce) * 8).to_bytes(16, "big")
    return _ghash(h, _pad16(nonce) + length).to_bytes(16, "big")


def _iter_blocks(data: bytes) -> Iterable[bytes]:
    for offset in range(0, len(data), 16):
        yield data[offset : offset + 16]


def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """Encrypt ``plaintext`` with AES-CBC and PKCS#7 padding."""
    if len(iv) != 16:
        raise ValueError("AES-CBC IV must be 16 bytes")
    aes = _AES(bytes(key))
    padding = 16 - len(plaintext) % 16
    padded = bytes(plaintext) + bytes([padding]) * padding

    previous = bytes(iv)
    output = bytearray()
    for offset in range(0, len(padded), 16):
        block = bytes(
            left ^ right
            for left, right in zip(padded[offset : offset + 16], previous)
        )
        previous = aes.encrypt_block(block)
        output.extend(previous)
    return bytes(output)


def aes_gcm_decrypt(
    key: bytes,
    nonce: bytes,
    ciphertext: bytes,
    aad: bytes = b"",
) -> bytes:
    """Decrypt ``ciphertext`` (with a 16-byte GCM tag appended)."""
    if len(ciphertext) < 16:
        raise ValueError("ciphertext is too short to contain a GCM tag")

    tag = ciphertext[-16:]
    body = ciphertext[:-16]
    aes = _AES(bytes(key))
    h = int.from_bytes(aes.encrypt_block(b"\x00" * 16), "big")
    j0 = _j0(aes, bytes(nonce))

    auth_data = (
        _pad16(bytes(aad))
        + _pad16(body)
        + (len(aad) * 8).to_bytes(8, "big")
        + (len(body) * 8).to_bytes(8, "big")
    )
    expected_tag = bytes(
        left ^ right
        for left, right in zip(
            aes.encrypt_block(j0), _ghash(h, auth_data).to_bytes(16, "big")
        )
    )
    if not hmac.compare_digest(expected_tag, tag):
        raise ValueError("AES-GCM authentication failed (wrong key or corrupt data)")

    counter = int.from_bytes(j0, "big")
    plaintext = bytearray()
    for block in _iter_blocks(body):
        counter = (counter & ~0xFFFFFFFF) | ((counter + 1) & 0xFFFFFFFF)
        keystream = aes.encrypt_block(counter.to_bytes(16, "big"))
        plaintext.extend(
            left ^ right for left, right in zip(block, keystream)
        )
    return bytes(plaintext)


__all__ = ["aes_cbc_encrypt", "aes_gcm_decrypt"]
