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
    _BaseUnivariateCategoricalSequenceValidator,
    _SingleUnivariateCategoricalSequenceValidator,
    _UnivariateCategoricalSequenceClassifierValidator,
)

__all__ = ['MultinomialHMM']

_defaults = SimpleNamespace(**{
    **HMM._defaults.__dict__,
    **dict(
        hmmlearn_kwargs=dict(
            init_params="ste",
            params="ste",
        )
    )
})

class MultinomialHMM(HMM):
    """A hidden Markov model with univariate multinomial emissions."""

    _base_sequence_validator = _BaseUnivariateCategoricalSequenceValidator
    _single_sequence_validator = _SingleUnivariateCategoricalSequenceValidator
    _sequence_classifier_validator = _UnivariateCategoricalSequenceClassifierValidator
    _defaults = _defaults

    def __init__(
        self,
        *,
        n_states: PositiveInt = _defaults.n_states,
        topology: Optional[Literal["ergodic", "left-right", "linear"]] = _defaults.topology,
        random_state: Optional[Union[NonNegativeInt, np.random.RandomState]] = _defaults.random_state,
        hmmlearn_kwargs: Dict[str, Any] = deepcopy(_defaults.hmmlearn_kwargs)
    ) -> MultinomialHMM:
        """
        :param n_states: Number of states in the Markov chain.
        :param topology: Transition topology of the Markov chain — see :ref:`topologies`.

          - If ``None``, behaves the same as ``'ergodic'`` but with `hmmlearn <https://hmmlearn.readthedocs.io/en/latest/>`__ initialization.

        :param random_state: Seed or :class:`numpy:numpy.random.RandomState` object for reproducible pseudo-randomness.
        :param hmmlearn_kwargs: Additional key-word arguments provided to the `hmmlearn <https://hmmlearn.readthedocs.io/en/latest/>`__ HMM constructor.
        """
        super().__init__(n_states, topology, random_state, hmmlearn_kwargs)

    def fit(
        self,
        X: Array[int],
        lengths: Optional[Array[int]] = None
    ) -> MultinomialHMM:
        """Fits the HMM to the provided observation sequences using the Baum—Welch algorithm.

        :param X: Univariate observation sequence(s).

            - Should be a single 1D array.
            - Should be a concatenated sequence if multiple sequences are provided,
              with respective sequence lengths being provided in the ``lengths`` argument for decoding the original sequences.

        :param lengths: Lengths of the observation sequences provided in ``X``.

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

        self.model = hmmlearn.hmm.MultinomialHMM(
            n_components=self.n_states,
            random_state=self.random_state_,
            **kwargs
        )

        for attr in ('startprob', 'transmat', 'emissionprob'):
            if hasattr(self, f'_{attr}'):
                setattr(self.model, f'{attr}_', getattr(self, f'_{attr}'))

        self.model.fit(data.X, lengths=data.lengths)
        self.n_seqs_ = len(data.lengths)

        return self

    @_requires_fit
    def score(
        self,
        x: Array[int],
    ) -> float:
        """Calculates the log-likelihood of the HMM generating a **single** observation sequence.

        :param x: Univariate observation sequence.

            - Should be a single 1D array.

        :note: This method requires a trained model — see :func:`fit`.

        :return: The log-likelihood.
        """
        return super().score(x)

    @_requires_fit
    def n_params(self) -> NonNegativeInt:
        n_params = super().n_params()
        if 'e' not in self._skip_params:
            n_params += self.model.emissionprob_.size
        return n_params

    @_requires_fit
    def bic(
        self,
        X: Array[int],
        lengths: Optional[Array[int]] = None
    ) -> float:
        """The Bayesian information criterion of the model, evaluated with the maximum likelihood of ``X``.

        :param X: Univariate observation sequence(s).

            - Should be a single 1D array.
            - Should be a concatenated sequence if multiple sequences are provided,
              with respective sequence lengths being provided in the ``lengths`` argument for decoding the original sequences.

        :param lengths: Lengths of the observation sequences provided in ``X``.

            - If ``None``, then ``X`` is assumed to be a single observation sequence.
            - ``len(X)`` should be equal to ``sum(lengths)``.

        :note: This method requires a trained model — see :func:`fit`.

        :return: The Bayesian information criterion.
        """
        return super().bic(X, lengths)

    @_requires_fit
    def aic(
        self,
        X: Array[int],
        lengths: Optional[Array[int]] = None
    ) -> float:
        """The Akaike information criterion of the model, evaluated with the maximum likelihood of ``X``.

        :param X: Univariate observation sequence(s).

            - Should be a single 1D array.
            - Should be a concatenated sequence if multiple sequences are provided,
              with respective sequence lengths being provided in the ``lengths`` argument for decoding the original sequences.

        :param lengths: Lengths of the observation sequences provided in ``X``.

            - If ``None``, then ``X`` is assumed to be a single observation sequence.
            - ``len(X)`` should be equal to ``sum(lengths)``.

        :note: This method requires a trained model — see :func:`fit`.

        :return: The Akaike information criterion.
        """
        return super().aic(X, lengths)

    def set_state_emissions(self, values: Array[float]):
        """Sets the state emission distribution of the HMM's emission model.

        If this method is **not** called, emission probabilities will be initialized by `hmmlearn <https://hmmlearn.readthedocs.io/en/latest/>`__.

        :param values: Array of emission probabilities.

        :note: If used, this method should normally be called before :func:`fit`.
        """
        self._emissionprob = Array[float].validate_type(values)
        self._skip_init_params |= set('e')

    def freeze(
        self,
        params: str = _defaults.hmmlearn_kwargs["params"],
    ):
        """Freezes the trainable parameters of the HMM's Markov chain and/or emission model,
        preventing them from being updated during the Baum—Welch algorithm.

        :param params: A string specifying which parameters to freeze. Can contain a combination of:

            - ``'s'`` for initial state probabilities (Markov chain parameters),
            - ``'t'`` for transition probabilities (Markov chain parameters),
            - ``'e'`` for emission probailities (emission parameters).

        :note: If used, this method should normally be called before :func:`fit`.

        See Also
        --------
        unfreeze:
            Unfreezes the trainable parameters of the HMM's Markov chain or emission model,
            allowing them to be updated during the Baum—Welch algorithm.
        """
        super().freeze(params)

    def unfreeze(
        self,
        params: str = _defaults.hmmlearn_kwargs["params"],
    ):
        """Unfreezes the trainable parameters of the HMM's Markov chain and/or emission model,
        allowing them to be updated during the Baum—Welch algorithm.

        :param params: A string specifying which parameters to unfreeze. Can contain a combination of:

            - ``'s'`` for initial state probabilities (Markov chain parameters),
            - ``'t'`` for transition probabilities (Markov chain parameters),
            - ``'e'`` for emission probailities (emission parameters).

        See Also
        --------
        freeze:
            Freezes the trainable parameters of the HMM's Markov chain and/or emission model,
            preventing them from being updated during the Baum—Welch algorithm.
        """
        super().freeze(params)

class _MultinomialHMMValidator(_HMMValidator):
    hmmlearn_kwargs: Dict[str, Any] = _defaults.hmmlearn_kwargs

    _class = MultinomialHMM

MultinomialHMM.__init__ = _validate_params(using=_MultinomialHMMValidator)(MultinomialHMM.__init__)