"""Pure Python Groth16 BN254 / BN128 Verifier using py_ecc.bn128.

Validates the bilinear pairing equation:
e(-A, B) * e(alpha, beta) * e(sum(public_inputs * IC), gamma) * e(C, delta) == 1_G_T
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple, Union
from py_ecc.bn128 import FQ, FQ2, FQ12, G1, G2, add, multiply, neg, pairing

from .codec import Groth16Proof, pad32


def parse_g1_point(point: Union[Sequence[Any], str]) -> Tuple[FQ, FQ]:
    """Parse G1 point (X, Y) into py_ecc (FQ, FQ)."""
    if isinstance(point, str):
        raw = bytes.fromhex(point[2:] if point.startswith("0x") else point)
        x = int.from_bytes(raw[0:32], "big")
        y = int.from_bytes(raw[32:64], "big")
        return (FQ(x), FQ(y))
    return (FQ(int(point[0])), FQ(int(point[1])))


def parse_g2_point(point: Union[Sequence[Any], str]) -> Tuple[FQ2, FQ2]:
    """Parse G2 point into py_ecc (FQ2, FQ2).

    Supports:
    - snarkjs format: [[c0, c1], [c0, c1]] where c0=imag, c1=real
    - flat EVM hex string (128 bytes: X1_real, X0_imag, Y1_real, Y0_imag)
    """
    if isinstance(point, str):
        raw = bytes.fromhex(point[2:] if point.startswith("0x") else point)
        # EVM format: X1_real, X0_imag, Y1_real, Y0_imag
        # In py_ecc, FQ2 is constructed as FQ2([c0, c1])
        x1 = int.from_bytes(raw[0:32], "big")
        x0 = int.from_bytes(raw[32:64], "big")
        y1 = int.from_bytes(raw[64:96], "big")
        y0 = int.from_bytes(raw[96:128], "big")
        return (FQ2([x0, x1]), FQ2([y0, y1]))

    # snarkjs [[x0, x1], [y0, y1]]
    x0 = int(point[0][0])
    x1 = int(point[0][1])
    y0 = int(point[1][0])
    y1 = int(point[1][1])
    return (FQ2([x0, x1]), FQ2([y0, y1]))


def verify_groth16_proof(
    proof: Union[Groth16Proof, Dict[str, Any]],
    public_signals: Sequence[Union[int, str]],
    verification_key: Dict[str, Any],
) -> bool:
    """Verifies a Groth16 proof on the BN254 / BN128 curve in 100% pure Python.

    Args:
        proof: Groth16Proof instance or snarkjs dict.
        public_signals: List of public scalar inputs.
        verification_key: SnarkJS or Arkworks verification key dict.

    Returns:
        True if the proof satisfies the pairing equation, False otherwise.
    """
    try:
        # 1. Parse proof points
        if isinstance(proof, Groth16Proof):
            a = parse_g1_point(proof.a_hex)
            b = parse_g2_point(proof.b_hex)
            c = parse_g1_point(proof.c_hex)
        else:
            p_dict = proof.get("proof", proof)
            if "pi_a" in p_dict:
                a = parse_g1_point(p_dict["pi_a"])
                b = parse_g2_point(p_dict["pi_b"])
                c = parse_g1_point(p_dict["pi_c"])
            else:
                a = parse_g1_point(p_dict["a"])
                b = parse_g2_point(p_dict["b"])
                c = parse_g1_point(p_dict["c"])

        # 2. Parse Verification Key
        vk = verification_key.get("vk", verification_key)
        alpha_1 = parse_g1_point(vk.get("vk_alpha_1") or vk.get("alpha_g1"))
        beta_2 = parse_g2_point(vk.get("vk_beta_2") or vk.get("beta_g2"))
        gamma_2 = parse_g2_point(vk.get("vk_gamma_2") or vk.get("gamma_g2"))
        delta_2 = parse_g2_point(vk.get("vk_delta_2") or vk.get("delta_g2"))

        ic_raw = vk.get("IC") or vk.get("gamma_abc_g1")
        if not ic_raw:
            raise ValueError("Verification key missing IC / gamma_abc_g1 points")

        ic_points = [parse_g1_point(pt) for pt in ic_raw]

        if len(public_signals) + 1 != len(ic_points):
            raise ValueError(
                f"Public signals count ({len(public_signals)}) + 1 != IC points count ({len(ic_points)})"
            )

        # 3. Compute linear combination of public inputs: vk_x = IC[0] + sum(IC[i+1] * pub[i])
        vk_x = ic_points[0]
        for pub_val, ic in zip(public_signals, ic_points[1:], strict=True):
            scalar = int(pub_val, 16) if isinstance(pub_val, str) and pub_val.startswith("0x") else int(pub_val)
            if scalar != 0:
                vk_x = add(vk_x, multiply(ic, scalar))

        # 4. Compute pairings:
        # e(-A, B) * e(alpha_1, beta_2) * e(vk_x, gamma_2) * e(C, delta_2) == 1_G_T
        p1 = pairing(b, neg(a))
        p2 = pairing(beta_2, alpha_1)
        p3 = pairing(gamma_2, vk_x)
        p4 = pairing(delta_2, c)

        result = p1 * p2 * p3 * p4
        return result == FQ12.one()
    except Exception:
        return False
