from kohaku.crypto.mimc import mimc_hash2
from kohaku.merkle.tree import MerkleTree


def test_merkle_tree_proofs():
    tree = MerkleTree(height=20, hash_fn=mimc_hash2)

    leaves = [111, 222, 333, 444, 555]
    indices = tree.insert_batch(leaves)

    assert len(indices) == 5
    assert indices == [0, 1, 2, 3, 4]

    root = tree.root()
    assert root > 0

    # Verify proof for each leaf
    for idx, leaf in zip(indices, leaves, strict=True):
        proof = tree.generate_proof(idx)
        assert proof.leaf == leaf
        assert proof.root == root
        assert proof.path_elements == proof.siblings
        assert proof.verify(hash_fn=mimc_hash2) is True


def test_lean_imt_dynamic_tree_and_proofs():
    from kohaku.crypto.poseidon import poseidon_hash2
    from kohaku.merkle.tree import LeanIMT, compute_lean_imt_root

    tree = LeanIMT(hash_fn=poseidon_hash2)
    assert tree.root() == 0

    # 1 leaf: odd node promoted directly without hashing with 0
    tree.insert(101)
    assert tree.root() == 101
    assert tree.depth == 0

    # 2 leaves: hash(101, 202)
    tree.insert(202)
    assert tree.root() == poseidon_hash2(101, 202)
    assert tree.depth == 1

    # 3 leaves: hash(hash(101, 202), 303) — leaf 303 promoted at level 0
    tree.insert(303)
    expected_3 = poseidon_hash2(poseidon_hash2(101, 202), 303)
    assert tree.root() == expected_3
    assert compute_lean_imt_root([101, 202, 303], poseidon_hash2) == expected_3
    assert tree.depth == 2

    for idx in range(3):
        proof = tree.generate_proof(idx)
        assert proof.verify(hash_fn=poseidon_hash2) is True

