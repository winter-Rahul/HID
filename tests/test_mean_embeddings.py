import numpy as np
import pytest
from src.pipeline import mean_embedding
from src.identity.face_recognizer import FaceRecognizer


def test_mean_embedding_is_normalized():
    features = [np.array([1., 0.]), np.array([0., 1.]), np.array([1., 0.])]
    result = mean_embedding(features)
    np.testing.assert_allclose(result, [2 / np.sqrt(5), 1 / np.sqrt(5)], rtol=1e-6)


@pytest.mark.parametrize("features", [[], [[1., 0.]], [[0., 0.]] * 3, [[float('nan'), 0.]] * 3])
def test_invalid_mean_embedding_is_rejected(features):
    with pytest.raises(ValueError):
        mean_embedding(features)


def test_enrollment_does_not_overwrite_existing_template(tmp_path):
    recognizer = FaceRecognizer.__new__(FaceRecognizer)
    recognizer.storage_file = str(tmp_path / 'users.json')
    recognizer.enrolled_users = {}
    assert recognizer.enroll_feature('Alice', np.array([3., 4.]))
    assert not recognizer.enroll_feature('Alice', np.array([1., 0.]))
    np.testing.assert_allclose(recognizer.enrolled_users['Alice'], [.6, .8])
