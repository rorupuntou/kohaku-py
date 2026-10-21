"""BN254 (alt_bn128) scalar field constants and arithmetic."""

# The prime field order for BN254 scalar field (used in Ethereum zk-SNARKs, Circom, Tornado, etc.)
SCALAR_FIELD_PRIME = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)
P = SCALAR_FIELD_PRIME


def to_field(val: int) -> int:
    """Reduces an integer modulo the BN254 scalar field prime."""
    return val % P


def add(a: int, b: int) -> int:
    return (a + b) % P


def sub(a: int, b: int) -> int:
    return (a - b) % P


def mul(a: int, b: int) -> int:
    return (a * b) % P


def inv(a: int) -> int:
    """Multiplicative inverse modulo P using Fermat's Little Theorem."""
    if a % P == 0:
        raise ZeroDivisionError("Cannot invert zero in field")
    return pow(a, P - 2, P)
