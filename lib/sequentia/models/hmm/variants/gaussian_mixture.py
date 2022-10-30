from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Optional, Union, Dict, Any, Literal
from pydantic import NonNegativeInt, PositiveInt

import numpy as np
import hmmlearn.hmm
from sklearn.utils import check_random_state

from sequentia.models.hmm.topologies import _topologies
from sequentia.models.hmm.variants.base import HMM, _HMMValidator
from sequentia.utils.decorators import _validate_params, _requires_fit
from sequentia.utils.validation import (
    Array,
    _BaseMultivariateFloatSequenceValidator,
    _SingleMultivariateFloatSequenceValidator,
    _MultivariateFloatSequenceClassifierValidator,
)

__all__ = ['GaussianMixtureHMM']

_defaults = SimpleNamespace(
    **{
        **HMM._defaults.__dict__,
        "n_components": 3,
        "covariance_type": "spherical",
        "hmmlearn_kwargs": dict(
            init_params="stmcw",
            params="stmcw",
        )
    }
)


class GaussianMixtureHMM(HMM):
    """A hidden Markov model with multivariate Gaussian mixture emissions.

    Examples
    --------
    Using a :class:`.GaussianMixtureHMM` to learn how to recognize spoken samples of the digit 3. ::

        import numpy as np
        from sequentia.datasets import load_digits
        from sequentia.models.hmm import GaussianMixtureHMM

        # Seed for reproducible pseudo-randomness
        random_state = np.random.RandomState(1)

        # Fetch MFCCs of spoken samples for the digit 3
        data = load_digits(numbers=[3], random_state=random_state)
        train_data, test_data = data.split(test_size=0.2)

        # Create and train a GaussianMixtureHMM to recognize the digit 3
        model = GaussianMixtureHMM(random_state=random_state)
        X_train, lengths_train = train_data.X_lengths
        model.fit(X_train, lengths_train)

        # Calculate the log-likelihood of the first test sample being generated by this model
        x, y = test_data[0]
        model.score(x)
    """

    _base_sequence_validator = _BaseMultivariateFloatSequenceValidator
    _single_sequence_validator = _SingleMultivariateFloatSequenceValidator
    _sequence_classifier_validator = _MultivariateFloatSequenceClassifierValidator
    _defaults = _defaults
    _unsettable_hmmlearn_kwargs = HMM._unsettable_hmmlearn_kwargs + ["n_components", "n_mix", "covariance_type"]

    def __init__(
        self,
        *,
        n_states: PositiveInt = _defaults.n_states,
        n_components: PositiveInt = _defaults.n_components,
        covariance_type: Literal["spherical", "diag", "full", "tied"] = _defaults.covariance_type,
        topology: Optional[Literal["ergodic", "left-right", "linear"]] = _defaults.topology,
        random_state: Optional[Union[NonNegativeInt, np.random.RandomState]] = _defaults.random_state,
        hmmlearn_kwargs: Dict[str, Any] = deepcopy(_defaults.hmmlearn_kwargs)
    ) -> GaussianMixtureHMM:
        """
        Initializes the :class:`.GaussianMixtureHMM`.

        :param n_states: Number of states in the Markov chain.
        :param n_components: Number of Gaussian components in the mixture emission distribution for each state.
        :param covariance_type: Type of covariance matrix in the mixture emission distribution for each state - see :ref:`covariance_types`.
        :param topology: Transition topology of the Markov chain — see :ref:`topologies`.

            - If ``None``, behaves the same as ``'ergodic'`` but with `hmmlearn <https://hmmlearn.readthedocs.io/en/latest/>`__ initialization.

        :param random_state: Seed or :class:`numpy:numpy.random.RandomState` object for reproducible pseudo-randomness.
        :param hmmlearn_kwargs: Additional key-word arguments provided to the `hmmlearn <https://hmmlearn.readthedocs.io/en/latest/>`__ HMM constructor.
        """
        super().__init__(n_states, topology, random_state, hmmlearn_kwargs)
        #: Number of Gaussian components in the emission model mixture distribution for each state.
        self.n_components = n_components
        #: Type of covariance matrix in the emission model mixture distribution for each state.
        self.covariance_type = covariance_type

    def fit(
        self,
        X: Array[float],
        lengths: Optional[Array[int]] = None
    ) -> GaussianMixtureHMM:
        """Fits the HMM to the sequences in ``X``, using the Baum—Welch algorithm.

        :param X: Univariate or multivariate observation sequence(s).

            - Should be a single 1D or 2D array.
            - Should have length as the 1st dimension and features as the 2nd dimension.
            - Should be a concatenated sequence if multiple sequences are provided,
              with respective sequence lengths being provided in the ``lengths`` argument for decoding the original sequences.

        :param lengths: Lengths of the observation sequence(s) provided in ``X``.

            - If ``None``, then ``X`` is assumed to be a single observation sequence.
            - ``len(X)`` should be equal to ``sum(lengths)``.

        :return: The fitted HMM.
        """
        data = self._base_sequence_validator(X=X, lengths=lengths)
        self.random_state_ = check_random_state(self.random_state)
        if self.topology is None:
            self.topology_ = None
        else:
            self.topology_ = _topologies[self.topology](self.n_states, self.random_state_)
        self._check_init_params()

        kwargs = self.hmmlearn_kwargs
        kwargs['init_params'] = ''.join(set(kwargs['init_params']) - self._skip_init_params)
        kwargs['params'] = ''.join(set(kwargs['params']) - self._skip_params)

        self.model = hmmlearn.hmm.GMMHMM(
            n_components=self.n_states,
            n_mix=self.n_components,
            covariance_type=self.covariance_type,
            random_state=self.random_state_,
            **kwargs
        )

        for attr in ('startprob', 'transmat', 'means', 'covars', 'weights'):
            if hasattr(self, f'_{attr}'):
                setattr(self.model, f'{attr}_', getattr(self, f'_{attr}'))

        self.model.fit(data.X, lengths=data.lengths)
        self.n_seqs_ = len(data.lengths)

        return self

    @_requires_fit
    def score(
        self,
        x: Array[float],
    ) -> float:
        """Calculates the log-likelihood of the HMM generating a single observation sequence.

        :param x: Univariate or multivariate observation sequence.

            - Should be a single 1D or 2D array.
            - Should have length as the 1st dimension and features as the 2nd dimension.

        :note: This method requires a trained model — see :func:`fit`.

        :return: The log-likelihood.
        """
        return super().score(x)

    @_requires_fit
    def n_params(self) -> NonNegativeInt:
        n_params = super().n_params()
        if 'm' not in self._skip_params:
            n_params += self.model.means_.size
        if 'c' not in self._skip_params:
            n_params += self.model.covars_.size
        if 'w' not in self._skip_params:
            n_params += self.model.weights_.size
        return n_params

    @_requires_fit
    def bic(
        self,
        X: Array[float],
        lengths: Optional[Array[int]] = None
    ) -> float:
        """The Bayesian information criterion of the model, evaluated with the maximum likelihood of ``X``.

        :param X: Univariate or multivariate observation sequence(s).

            - Should be a single 1D or 2D array.
            - Should have length as the 1st dimension and features as the 2nd dimension.
            - Should be a concatenated sequence if multiple sequences are provided,
              with respective sequence lengths being provided in the ``lengths`` argument for decoding the original sequences.

        :param lengths: Lengths of the observation sequence(s) provided in ``X``.

            - If ``None``, then ``X`` is assumed to be a single observation sequence.
            - ``len(X)`` should be equal to ``sum(lengths)``.

        :note: This method requires a trained model — see :func:`fit`.

        :return: The Bayesian information criterion.
        """
        return super().bic(X, lengths)

    @_requires_fit
    def aic(
        self,
        X: Array[float],
        lengths: Optional[Array[int]] = None
    ) -> float:
        """The Akaike information criterion of the model, evaluated with the maximum likelihood of ``X``.

        :param X: Univariate or multivariate observation sequence(s).

            - Should be a single 1D or 2D array.
            - Should have length as the 1st dimension and features as the 2nd dimension.
            - Should be a concatenated sequence if multiple sequences are provided,
              with respective sequence lengths being provided in the ``lengths`` argument for decoding the original sequences.

        :param lengths: Lengths of the observation sequence(s) provided in ``X``.

            - If ``None``, then ``X`` is assumed to be a single observation sequence.
            - ``len(X)`` should be equal to ``sum(lengths)``.

        :note: This method requires a trained model — see :func:`fit`.

        :return: The Akaike information criterion.
        """
        return super().aic(X, lengths)

    def set_state_means(self, values: Array[float]):
        """Sets the mean vectors of the state emission distributions.

        If this method is **not** called, mean vectors will be initialized by `hmmlearn <https://hmmlearn.readthedocs.io/en/latest/>`__.

        :param values: Array of emission distribution mean values.

        :note: If used, this method should normally be called before :func:`fit`.
        """
        self._means = Array[float].validate_type(values)
        self._skip_init_params |= set('m')

    def set_state_covariances(self, values: Array[float]):
        """Sets the covariance matrices of the state emission distributions.

        If this method is **not** called, covariance matrices will be initialized by `hmmlearn <https://hmmlearn.readthedocs.io/en/latest/>`__.

        :param values: Array of emission distribution covariance values.

        :note: If used, this method should normally be called before :func:`fit`.
        """
        self._covars = Array[float].validate_type(values)
        self._skip_init_params |= set('c')

    def set_state_weights(self, values: Array[float]):
        """Sets the component mixture weights of the state emission distributions.

        If this method is **not** called, component mixture weights will be initialized by `hmmlearn <https://hmmlearn.readthedocs.io/en/latest/>`__.

        :param values: Array of emission distribution component mixture weights.

        :note: If used, this method should normally be called before :func:`fit`.
        """
        self._weights = Array[float].validate_type(values)
        self._skip_init_params |= set('w')

    def freeze(
        self,
        params: str = _defaults.hmmlearn_kwargs["params"],
    ):
        """Freezes the trainable parameters of the HMM, preventing them from being updated during the Baum—Welch algorithm.

        :param params: A string specifying which parameters to freeze. Can contain a combination of:

            - ``'s'`` for initial state probabilities,
            - ``'t'`` for transition probabilities,
            - ``'m'`` for emission distribution means,
            - ``'c'`` for emission distribution covariances,
            - ``'w'`` for emission distribution mixture weights.

        :note: If used, this method should normally be called before :func:`fit`.

        See Also
        --------
        unfreeze:
            Unfreezes the trainable parameters of the HMM, allowing them to be updated during the Baum—Welch algorithm.
        """
        super().freeze(params)

    def unfreeze(
        self,
        params: str = _defaults.hmmlearn_kwargs["params"],
    ):
        """Unfreezes the trainable parameters of the HMM, allowing them to be updated during the Baum—Welch algorithm.

        :param params: A string specifying which parameters to unfreeze. Can contain a combination of:

            - ``'s'`` for initial state probabilities,
            - ``'t'`` for transition probabilities,
            - ``'m'`` for emission distribution means,
            - ``'c'`` for emission distribution covariances,
            - ``'w'`` for emission distribution mixture weights.

        See Also
        --------
        freeze:
            Freezes the trainable parameters of the HMM, preventing them from be updated during the Baum—Welch algorithm.
        """
        super().freeze(params)

class _GaussianMixtureHMMValidator(_HMMValidator):
    n_components: PositiveInt = _defaults.n_components
    covariance_type: Literal["spherical", "diag", "full", "tied"] = _defaults.covariance_type
    hmmlearn_kwargs: Dict[str, Any] = _defaults.hmmlearn_kwargs

    _class = GaussianMixtureHMM

GaussianMixtureHMM.__init__ = _validate_params(using=_GaussianMixtureHMMValidator)(GaussianMixtureHMM.__init__)
