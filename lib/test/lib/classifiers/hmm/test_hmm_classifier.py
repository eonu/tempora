import os, pickle, pytest, warnings, os, numpy as np, hmmlearn.hmm
from copy import deepcopy
from sequentia.classifiers import GMMHMM, HMMClassifier, _ErgodicTopology
from ....support import assert_equal, assert_not_equal

# Set seed for reproducible randomness
seed = 0
np.random.seed(seed)
rng = np.random.RandomState(seed)

# Set of possible labels
labels = ['c{}'.format(i) for i in range(5)]

# Create and fit some sample HMMs
hmms = []
for i, label in enumerate(labels):
    hmm = GMMHMM(label=label, n_states=(i + 3), random_state=rng)
    hmm.set_random_initial()
    hmm.set_random_transitions()
    hmm.fit([np.arange((i + j * 20) * 30).reshape(-1, 3) for j in range(2, 5)])
    hmms.append(hmm)

# Create some sample test data and labels
X = [np.arange((i + 2 * 20) * 30).reshape(-1, 3) for i in range(2, 5)]
Y = ['c0', 'c1', 'c1']
x, y = X[0], 'c1'

# Fit a classifier
hmm_clf = HMMClassifier()
hmm_clf.fit(hmms)

# =================== #
# HMMClassifier.fit() #
# =================== #

def test_fit_list():
    """Fit the classifier using a list of HMMs"""
    clf = HMMClassifier()
    clf.fit(hmms)
    assert clf._models == hmms

def test_fit_list_empty():
    """Fit the classifier using an empty list"""
    clf = HMMClassifier()
    with pytest.raises(RuntimeError) as e:
        clf.fit([])
    assert str(e.value) == 'The classifier must be fitted with at least one HMM'

def test_fit_list_invalid():
    """Fit the classifier using a list of invalid types"""
    clf = HMMClassifier()
    with pytest.raises(TypeError) as e:
        clf.fit(['a', 'b'])
    assert str(e.value) == 'Expected all models to be GMMHMM objects'

# ======================= #
# HMMClassifier.predict() #
# ======================= #

def test_predict_single_frequency_prior():
    """Predict a single observation sequence with a frequency prior"""
    prediction = hmm_clf.predict(x, prior='frequency', return_scores=False, original_labels=False)
    assert prediction == 4

def test_predict_single_uniform_prior():
    prediction = hmm_clf.predict(x, prior='uniform', return_scores=False, original_labels=False)
    assert prediction == 4

def test_predict_single_custom_prior():
    prediction = hmm_clf.predict(x, prior=([1-4e-10]+[1e-10]*4), return_scores=False, original_labels=False)
    assert prediction == 0

def test_predict_single_return_scores():
    prediction = hmm_clf.predict(x, prior='frequency', return_scores=True, original_labels=False)
    assert isinstance(prediction, tuple)
    assert prediction[0] == 4
    assert_equal(prediction[1], np.array([
        -1224.7910008 , -1302.74962802, -1269.35306368, -1230.59148179, -1222.21963107
    ]))

def test_predict_single_original_labels():
    prediction = hmm_clf.predict(x, prior='uniform', return_scores=False, original_labels=True)
    assert prediction == 'c4'

def test_predict_single_return_scores_original_labels():
    prediction = hmm_clf.predict(x, prior='frequency', return_scores=True, original_labels=True)
    assert isinstance(prediction, tuple)
    assert prediction[0] == 'c4'
    assert_equal(prediction[1], np.array([
        -1224.7910008 , -1302.74962802, -1269.35306368, -1230.59148179, -1222.21963107
    ]))

def test_predict_multiple_frequency_prior():
    """Predict multiple observation sequences with a frequency prior"""
    predictions = hmm_clf.predict(X, prior='frequency', return_scores=False, original_labels=False)
    assert_equal(predictions, np.array([4, 4, 0]))

def test_predict_multiple_uniform_prior():
    predictions = hmm_clf.predict(X, prior='uniform', return_scores=False, original_labels=False)
    assert_equal(predictions, np.array([4, 4, 0]))

def test_predict_multiple_custom_prior():
    predictions = hmm_clf.predict(X, prior=([1-4e-10]+[1e-10]*4), return_scores=False, original_labels=False)
    assert_equal(predictions, np.array([0, 0, 0]))

def test_predict_multiple_return_scores():
    predictions = hmm_clf.predict(X, prior='frequency', return_scores=True, original_labels=False)
    assert isinstance(predictions, tuple)
    assert_equal(predictions[0], np.array([4, 4, 0]))
    assert_equal(predictions[1], np.array([
        [-1224.7910008 , -1302.74962802, -1269.35306368, -1230.59148179, -1222.21963107],
        [-1253.13158379, -1331.2088869 , -1303.04688636, -1259.4763248 , -1251.90302358],
        [-1281.50581789, -1359.72306473, -1335.76859787, -1288.46683118, -1281.66788896]
    ]))

def test_predict_multiple_original_labels():
    predictions = hmm_clf.predict(X, prior='frequency', return_scores=False, original_labels=True)
    assert all(np.equal(predictions.astype(object), np.array(['c4', 'c4', 'c0'], dtype=object)))

def test_predict_multiple_return_scores_original_labels():
    predictions = hmm_clf.predict(X, prior='frequency', return_scores=True, original_labels=True)
    assert isinstance(predictions, tuple)
    assert all(np.equal(predictions[0].astype(object), np.array(['c4', 'c4', 'c0'], dtype=object)))
    assert_equal(predictions[1], np.array([
        [-1224.7910008 , -1302.74962802, -1269.35306368, -1230.59148179, -1222.21963107],
        [-1253.13158379, -1331.2088869 , -1303.04688636, -1259.4763248 , -1251.90302358],
        [-1281.50581789, -1359.72306473, -1335.76859787, -1288.46683118, -1281.66788896]
    ]))

# ======================== #
# HMMClassifier.evaluate() #
# ======================== #

def test_evaluate():
    acc, cm = hmm_clf.evaluate(X, Y, prior='frequency')
    assert acc == 0.0
    assert_equal(cm, np.array([
        [0, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0]
    ]))

# ===================================== #
# HMMClassifier (serialize/deserialize) #
# ===================================== #

def test_serialization():
    model_file = 'test.pkl'
    try:
        with open(model_file, 'wb') as file:
            pickle.dump(hmm_clf, file)
        with open(model_file, 'rb') as file:
            clf = pickle.load(file)
            predictions = clf.predict(X, prior='frequency', return_scores=True, original_labels=True)
            assert isinstance(predictions, tuple)
            assert all(np.equal(predictions[0].astype(object), np.array(['c4', 'c4', 'c0'], dtype=object)))
            assert_equal(predictions[1], np.array([
                [-1224.7910008 , -1302.74962802, -1269.35306368, -1230.59148179, -1222.21963107],
                [-1253.13158379, -1331.2088869 , -1303.04688636, -1259.4763248 , -1251.90302358],
                [-1281.50581789, -1359.72306473, -1335.76859787, -1288.46683118, -1281.66788896]
            ]))
    finally:
        if os.path.exists(model_file):
            os.remove(model_file)