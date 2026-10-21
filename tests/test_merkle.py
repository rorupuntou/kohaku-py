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
        assert proof.verify(hash_fn=mimc_hash2) is True
