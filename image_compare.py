import numpy as np
from PIL import Image


def compare(image_a: Image.Image, image_b: Image.Image) -> float:
    """Compare two PIL images and return a similarity score between 0.0 and 1.0.

    Uses Mean Squared Error normalized to a 0-1 similarity scale.
    1.0 = identical, 0.0 = completely different.
    """
    a = np.asarray(image_a, dtype=np.float64)
    b = np.asarray(image_b, dtype=np.float64)

    # Resize b to match a if dimensions differ
    if a.shape != b.shape:
        image_b = image_b.resize((image_a.width, image_a.height))
        b = np.asarray(image_b, dtype=np.float64)

    mse = np.mean((a - b) ** 2)
    # Max possible MSE for 8-bit images is 255^2 = 65025
    similarity = 1.0 - (mse / 65025.0)
    return max(0.0, min(1.0, similarity))
