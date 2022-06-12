import warnings, numpy as np, pickle
from tqdm.auto import tqdm
from joblib import Parallel, delayed
from multiprocessing import cpu_count
from .gmmhmm import GMMHMM
from sklearn.metrics import confusion_matrix
from sklearn.preprocessing import LabelEncoder
from ...internals import _Validator

class HMMClassifier:
    """A classifier that combines individual :class:`~GMMHMM` objects, which each model sequences from a different class.

    Attributes
    ----------
    models_ (property): list of GMMHMM
        A collection of the :class:`~GMMHMM` objects to use for classification.

    encoder_ (property): sklearn.preprocessing.LabelEncoder
        The label encoder fitted on the set of ``classes`` provided during instantiation.

    classes_ (property): numpy.ndarray (str/numeric)
        The complete set of possible classes/labels.
    """

    def __init__(self):
        self._val = _Validator()

    def fit(self, models):
        """Fits the classifier with a collection of :class:`~GMMHMM` objects.

        Parameters
        ----------
        models: array-like of GMMHMM
            A collection of :class:`~GMMHMM` objects to use for classification.
        """

        models = list(self._val.is_iterable(models, 'models'))
        if not all(isinstance(model, GMMHMM) for model in models):
            raise TypeError('Expected all models to be GMMHMM objects')

        if len(models) > 0:
            self._models_ = models
        else:
            raise RuntimeError('The classifier must be fitted with at least one HMM')

        self._encoder_ = LabelEncoder()
        self._encoder_.fit([model.label for model in models])

    def predict(self, X, prior='frequency', return_scores=False, original_labels=True, verbose=True, n_jobs=1):
        """Predicts the label for an observation sequence (or multiple sequences) according to maximum likelihood or posterior scores.

        Parameters
        ----------
        X: numpy.ndarray (float) or list of numpy.ndarray (float)
            An individual observation sequence or a list of multiple observation sequences.

        prior: {'frequency', 'uniform'} or array-like of float
            How the prior probability for each model is calculated to perform MAP estimation by scoring with
            the joint probability (or un-normalized posterior) :math:`\\mathbb{P}(O, \\lambda_c)=\\mathbb{P}(O|\\lambda_c)\\mathbb{P}(\\lambda_c)`.

            - `'frequency'`: Calculate the prior probability :math:`\\mathbb{P}(\\lambda_c)` as the proportion of training examples in class :math:`c`.
            - `'uniform'`: Set the priors uniformly such that :math:`\\mathbb{P}(\\lambda_c)=\\frac{1}{C}` for each class :math:`c\\in\\{1,\\ldots,C\\}` (**equivalent to ignoring the prior**).

            Alternatively, class prior probabilities can be specified in an iterable of floats, e.g. `[0.1, 0.3, 0.6]`.

        return_scores: bool
            Whether to return the scores of each model on the observation sequence(s).

        original_labels: bool
            Whether to inverse-transform the labels to their original encoding.

        verbose: bool
            Whether to display a progress bar or not.

            .. note::
                If both ``verbose=True`` and ``n_jobs > 1``, then the progress bars for each process
                are always displayed in the console, regardless of where you are running this function from
                (e.g. a Jupyter notebook).

        n_jobs: int > 0 or -1
            | The number of jobs to run in parallel.
            | Setting this to -1 will use all available CPU cores.

        Returns
        -------
        prediction(s): str/numeric or :class:`numpy:numpy.ndarray` (str/numeric)
            The predicted label(s) for the observation sequence(s).

            If ``original_labels`` is true, then the returned labels are inverse-transformed into their original encoding.

        scores: :class:`numpy:numpy.ndarray` (float)
            An :math:`N\\times M` matrix of scores (unnormalized log posteriors), for each of the :math:`N` observation sequences,
            for each of the :math:`M` HMMs. Only returned if ``return_scores`` is true.
        """
        self.models_
        X = self._val.is_observation_sequences(X, allow_single=True)
        if not isinstance(prior, str):
            self._val.is_iterable(prior, 'prior')
            assert len(prior) == len(self._models_), 'There must be a class prior for each HMM or class'
            assert all(isinstance(p, (int, float)) for p in prior), 'Class priors must be numerical'
            assert all(0. <= p <= 1. for p in prior), 'Class priors must each be between zero and one'
            assert np.isclose(sum(prior), 1.), 'Class priors must form a probability distribution by summing to one'
        else:
            self._val.is_one_of(prior, ['frequency', 'uniform'], desc='prior')
        self._val.is_boolean(return_scores, desc='return_scores')
        self._val.is_boolean(original_labels, desc='original_labels')
        self._val.is_boolean(verbose, desc='verbose')
        self._val.is_restricted_integer(n_jobs, lambda x: x == -1 or x > 0, 'number of jobs', '-1 or greater than zero')

        n_jobs = min(cpu_count() if n_jobs == -1 else n_jobs, len(X))
        priors = self._get_priors(prior)

        # Make prediction for a single sequence
        if isinstance(X, np.ndarray):
            if n_jobs > 1:
                warnings.warn('Single predictions do not yet support multi-processing. Set n_jobs=1 to silence this warning.')

            scores = self._predict(X, priors=priors, verbose=verbose)
            labels = scores.argmax()

        # Make predictions for multiple sequences (in parallel)
        else:
            if n_jobs == 1:
                # Use entire list as a chunk
                scores = self._chunk_predict(X, priors=priors, verbose=verbose)

            else:
                if verbose:
                    warnings.warn('Progress bars cannot be displayed when using multiple processes. Set verbose=False to silence this warning.')

                # Split X into n_jobs equally sized chunks and process in parallel
                chunks = [list(chunk) for chunk in np.array_split(np.array(X, dtype=object), n_jobs)]
                scores = np.vstack(Parallel(n_jobs=n_jobs)(delayed(self._chunk_predict)(chunk, priors) for chunk in chunks))

            labels = scores.argmax(axis=1)

        return self._output(labels, scores, return_scores=return_scores, original_labels=original_labels)

    def evaluate(self, X, y, prior='frequency', verbose=True, n_jobs=1):
        """Evaluates the performance of the classifier on a batch of observation sequences and their labels.

        Parameters
        ----------
        X: list of numpy.ndarray (float)
            A list of multiple observation sequences.

        y: array-like of str/numeric
            An iterable of labels for the observation sequences.

        prior: {'frequency', 'uniform'} or array-like of float
            How the prior probability for each model is calculated to perform MAP estimation by scoring with
            the joint probability (or un-normalized posterior) :math:`\\mathbb{P}(O, \\lambda_c)=\\mathbb{P}(O|\\lambda_c)\\mathbb{P}(\\lambda_c)`.

            - `'frequency'`: Calculate the prior probability :math:`\\mathbb{P}(\\lambda_c)` as the proportion of training examples in class :math:`c`.
            - `'uniform'`: Set the priors uniformly such that :math:`\\mathbb{P}(\\lambda_c)=\\frac{1}{C}` for each class :math:`c\\in\\{1,\\ldots,C\\}` (**equivalent to ignoring the prior**).

            Alternatively, class prior probabilities can be specified in an iterable of floats, e.g. `[0.1, 0.3, 0.6]`.

        verbose: bool
            Whether to display a progress bar or not.

            .. note::
                If both ``verbose=True`` and ``n_jobs > 1``, then the progress bars for each process
                are always displayed in the console, regardless of where you are running this function from
                (e.g. a Jupyter notebook).

        n_jobs: int > 0 or -1
            | The number of jobs to run in parallel.
            | Setting this to -1 will use all available CPU cores.

        Returns
        -------
        accuracy: float
            The categorical accuracy of the classifier on the observation sequences.

        confusion: :class:`numpy:numpy.ndarray` (int)
            The confusion matrix representing the discrepancy between predicted and actual labels.
        """
        X, y = self._val.is_observation_sequences_and_labels(X, y)
        predictions = self.predict(X, prior=prior, return_scores=False, original_labels=False, verbose=verbose, n_jobs=n_jobs)
        cm = confusion_matrix(self._encoder_.transform(y), predictions, labels=self._encoder_.transform(self._encoder_.classes_))
        return np.sum(np.diag(cm)) / np.sum(cm), cm

    def save(self, path):
        """Serializes the :class:`HMMClassifier` object by pickling.

        Parameters
        ----------
        path: str
            File path (usually with `.pkl` extension) to store the serialized :class:`HMMClassifier` object.
        """
        self.models_
        with open(path, 'wb') as file:
            pickle.dump(self, file)

    @classmethod
    def load(cls, path):
        """Deserializes a :class:`HMMClassifier` object which was serialized with the :meth:`save` function.

        Parameters
        ----------
        path: str
            File path of the serialized data generated by the :meth:`save` method.

        Returns
        -------
        deserialized: :class:`HMMClassifier`
            The deserialized HMM classifier object.
        """
        with open(path, 'rb') as file:
            return pickle.load(file)

    def _get_priors(self, prior):
        """Fetch class prior probabilities."""
        if prior == 'frequency':
            total_seqs = sum(model.n_seqs_ for model in self._models_)
            return {model.label:(model.n_seqs_ / total_seqs) for model in self._models_}
        elif prior == 'uniform':
            return {model.label:(1. / len(self._models_)) for model in self._models_}
        else:
            return {model.label:prior[self._encoder_.transform([model.label]).item()] for model in self._models_}

    def _predict(self, x, priors, verbose=False):
        """Calculates the (unnormalized) class posteriors as a sum of the log forward probabilities and log priors."""
        return np.array([model.forward(x) + np.log(priors[model.label]) for model in tqdm(self._models_, desc='Calculating posteriors', disable=not(verbose))])

    def _chunk_predict(self, chunk, priors, verbose=False):
        """Makes predictions for multiple observation sequences."""
        return np.stack([self._predict(x, priors, verbose=False) for x in tqdm(chunk, desc='Predicting', disable=not(verbose))])

    def _output(self, idx, scores, return_scores, original_labels):
        """Inverse-transforms the labels if necessary, and returns them along with the scores."""
        if not original_labels:
            labels = idx
        else:
            if isinstance(idx, np.ndarray):
                labels = self._encoder_.inverse_transform(idx)
            else:
                labels = self._encoder_.inverse_transform([idx]).item()
        return (labels, scores) if return_scores else labels

    @property
    def models_(self):
        return self._val.is_fitted(self,
            lambda self: self._models_,
            'No models available - the classifier must be fitted first'
        )

    @property
    def encoder_(self):
        return self._encoder_

    @property
    def classes_(self):
        return self._encoder_.classes_

    def __repr__(self):
        name = '.'.join([self.__class__.__module__.split('.')[0], self.__class__.__name__])
        out = '{}('.format(name)
        try:
            self._models_
            out += 'models=[\n    '
            out += ',\n    '.join(repr(model) for model in self._models_)
            out += '\n]'
        except AttributeError:
            pass
        return '{})'.format(out)