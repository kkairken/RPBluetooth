"""
Face embedding matcher.
Compares face embeddings using cosine similarity.
"""
import numpy as np
import logging
from typing import List, Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)


class FaceMatcher:
    """Matches face embeddings against database."""

    def __init__(self, similarity_threshold: float = 0.6):
        """
        Initialize face matcher.

        Args:
            similarity_threshold: Minimum cosine similarity for a match
        """
        self.similarity_threshold = similarity_threshold

    def cosine_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score [0, 1]
        """
        try:
            # Normalize embeddings
            norm1 = np.linalg.norm(embedding1)
            norm2 = np.linalg.norm(embedding2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            # Compute cosine similarity
            similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

            # Clamp to [0, 1]
            similarity = float(np.clip(similarity, 0.0, 1.0))

            return similarity

        except Exception as e:
            logger.error(f"Cosine similarity computation error: {e}")
            return 0.0

    def find_best_match(
        self,
        query_embedding: np.ndarray,
        employee_embeddings: List[Tuple[Dict[str, Any], List[np.ndarray]]]
    ) -> Tuple[Optional[str], float, Optional[str]]:
        """
        Find best matching employee for a query embedding.

        Args:
            query_embedding: Query face embedding
            employee_embeddings: List of (employee_dict, embeddings_list) tuples

        Returns:
            Tuple of (employee_id, best_score, display_name) or (None, 0.0, None)
        """
        best_employee_id = None
        best_score = 0.0
        best_display_name = None

        for employee, embeddings in employee_embeddings:
            employee_id = employee['employee_id']
            display_name = employee.get('display_name')

            # Compare with all embeddings for this employee
            for embedding in embeddings:
                similarity = self.cosine_similarity(query_embedding, embedding)

                if similarity > best_score:
                    best_score = similarity
                    best_employee_id = employee_id
                    best_display_name = display_name

        # Check threshold
        if best_score < self.similarity_threshold:
            logger.debug(f"Best match score {best_score:.3f} below threshold {self.similarity_threshold}")
            return None, best_score, None

        logger.info(f"Matched employee {best_employee_id} with score {best_score:.3f}")
        return best_employee_id, best_score, best_display_name

    def match_with_details(
        self,
        query_embedding: np.ndarray,
        employee_embeddings: List[Tuple[Dict[str, Any], List[np.ndarray]]],
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find top K matching employees with detailed scores.

        Args:
            query_embedding: Query face embedding
            employee_embeddings: List of (employee_dict, embeddings_list) tuples
            top_k: Number of top matches to return

        Returns:
            List of match dictionaries with employee info and scores
        """
        all_matches = []

        for employee, embeddings in employee_embeddings:
            employee_id = employee['employee_id']
            display_name = employee.get('display_name')

            # Find best score among all embeddings for this employee
            best_similarity = 0.0
            for embedding in embeddings:
                similarity = self.cosine_similarity(query_embedding, embedding)
                if similarity > best_similarity:
                    best_similarity = similarity

            all_matches.append({
                'employee_id': employee_id,
                'display_name': display_name,
                'similarity': best_similarity,
                'is_match': best_similarity >= self.similarity_threshold
            })

        # Sort by similarity
        all_matches.sort(key=lambda x: x['similarity'], reverse=True)

        # Return top K
        return all_matches[:top_k]
