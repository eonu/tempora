import warnings

import numpy as np

class _Topology:
    """Represents a topology for a HMM, imposing restrictions on the transition matrix and initial state distribution.

    Parameters
    ----------
    n_states: int
        Number of states in the HMM.

    random_state: numpy.random.RandomState
        A random state object for reproducible randomness.
    """

    def __init__(self, n_states: int, random_state: np.random.RandomState):
        self.n_states = n_states
        self.random_state = random_state

    def uniform_start_probs(self) -> np.ndarray:
        """Sets the initial state distribution as a discrete uniform distribution.

        Returns
        -------
        initial: :class:`numpy:numpy.ndarray` (float)
            The initial state distribution of shape `(n_states,)`.
        """
        return np.ones(self.n_states) / self.n_states

    def random_start_probs(self) -> np.ndarray:
        """Sets the initial state distribution by randomly sampling probabilities generated by a Dirichlet distribution.

        Returns
        -------
        initial: :class:`numpy:numpy.ndarray` (float)
            The initial state distribution of shape `(n_states,)`.
        """
        return self.random_state.dirichlet(np.ones(self.n_states), size=1).flatten()

    def uniform_transitions(self) -> np.ndarray:
        """Sets the transition matrix as uniform (equal probability of transitioning
        to all other possible states from each state) corresponding to the topology.

        Returns
        -------
        transitions: :class:`numpy:numpy.ndarray` (float)
            The uniform transition matrix of shape `(n_states, n_states)`.
        """
        raise NotImplementedError

    def random_transitions(self) -> np.ndarray:
        """Sets the transition matrix as random (random probability of transitioning
        to all other possible states from each state) by sampling probabilities
        from a Dirichlet distribution - according to the topology.

        Returns
        -------
        transitions: :class:`numpy:numpy.ndarray` (float)
            The random transition matrix of shape `(n_states, n_states)`.
        """
        raise NotImplementedError

    def check_start_probs(self, initial: np.ndarray) -> None:
        """Validates an initial state distribution according to the topology's restrictions.

        Parameters
        ----------
        initial: numpy.ndarray (float)
            The initial state distribution to validate.
        """
        if not isinstance(initial, np.ndarray):
            raise TypeError('Initial state distribution must be a numpy.ndarray')
        if not initial.shape == (self.n_states,):
            raise ValueError('Initial state distribution must be of shape (n_states,)')
        if not np.isclose(initial.sum(), 1):
            raise ValueError('Initial state distribution must sum to one')
        return initial

    def check_transitions(self, transitions: np.ndarray) -> np.ndarray:
        """Validates a transition matrix according to the topology's restrictions.

        Parameters
        ----------
        transitions: numpy.ndarray (float)
            The transition matrix to validate.
        """
        if not isinstance(transitions, np.ndarray):
            raise TypeError('Transition matrix must be a numpy.ndarray')
        if not transitions.shape == (self.n_states, self.n_states):
            raise ValueError('Transition matrix must be of shape (n_states, n_states)')
        if not np.allclose(transitions.sum(axis=1), np.ones(self.n_states)):
            raise ValueError('Transition probabilities out of each state must sum to one')
        return transitions

class _ErgodicTopology(_Topology):
    """Represents the topology for an ergodic HMM, imposing non-zero probabilities in the transition matrix.

    Parameters
    ----------
    n_states: int
        Number of states in the HMM.

    random_state: numpy.random.RandomState
        A random state object for reproducible randomness.
    """

    name = "ergodic"

    def uniform_transitions(self) -> np.ndarray:
        """Sets the transition matrix as uniform (equal probability of transitioning
            to all other possible states from each state) corresponding to the topology.

        Returns
        -------
        transitions: :class:`numpy:numpy.ndarray` (float)
            The uniform transition matrix of shape `(n_states, n_states)`.
        """
        return np.ones((self.n_states, self.n_states)) / self.n_states

    def random_transitions(self) -> np.ndarray:
        """Sets the transition matrix as random (random probability of transitioning
        to all other possible states from each state) by sampling probabilities
        from a Dirichlet distribution - according to the topology.

        Returns
        -------
        transitions: :class:`numpy:numpy.ndarray` (float)
            The random transition matrix of shape `(n_states, n_states)`.
        """
        return self.random_state.dirichlet(np.ones(self.n_states), size=self.n_states)

    def check_transitions(self, transitions: np.ndarray) -> np.ndarray:
        """Validates a transition matrix according to the topology's restrictions.

        Parameters
        ----------
        transitions: numpy.ndarray (float)
            The transition matrix to validate.
        """
        super().check_transitions(transitions)
        if not np.all(transitions > 0):
            warnings.warn('Zero probabilities in ergodic transition matrix - these transition probabilities will not be learned')
        return transitions

class _LeftRightTopology(_Topology):
    """Represents the topology for a left-right HMM, imposing an upper-triangular transition matrix.

    Parameters
    ----------
    n_states: int
        Number of states in the HMM.

    random_state: numpy.random.RandomState
        A random state object for reproducible randomness.
    """

    name = "left-right"

    def uniform_transitions(self) -> np.ndarray:
        """Sets the transition matrix as uniform (equal probability of transitioning
            to all other possible states from each state) corresponding to the topology.

        Returns
        -------
        transitions: :class:`numpy:numpy.ndarray` (float)
            The uniform transition matrix of shape `(n_states, n_states)`.
        """
        upper_ones = np.triu(np.ones((self.n_states, self.n_states)))
        upper_divisors = np.triu(np.tile(np.arange(self.n_states, 0, -1), (self.n_states, 1)).T)
        lower_ones = np.tril(np.ones(self.n_states), k=-1)
        return upper_ones / (upper_divisors + lower_ones)

    def random_transitions(self) -> np.ndarray:
        """Sets the transition matrix as random (random probability of transitioning
        to all other possible states from each state) by sampling probabilities
        from a Dirichlet distribution, according to the topology.

        Returns
        -------
        transitions: :class:`numpy:numpy.ndarray` (float)
            The random transition matrix of shape `(n_states, n_states)`.
        """
        transitions = np.zeros((self.n_states, self.n_states))
        for i, row in enumerate(transitions):
            row[i:] = self.random_state.dirichlet(np.ones(self.n_states - i))
        return transitions

    def check_transitions(self, transitions: np.ndarray) -> np.ndarray:
        """Validates a transition matrix according to the topology's restrictions.

        Parameters
        ----------
        transitions: numpy.ndarray (float)
            The transition matrix to validate.
        """
        super().check_transitions(transitions)
        if not np.allclose(transitions, np.triu(transitions)):
            raise ValueError('Left-right transition matrix must be upper-triangular')
        return transitions

class _LinearTopology(_LeftRightTopology):
    """Represents the topology for a linear HMM.

    Parameters
    ----------
    n_states: int
        Number of states in the HMM.

    random_state: numpy.random.RandomState
        A random state object for reproducible randomness.
    """

    name = "linear"

    def uniform_transitions(self) -> np.ndarray:
        """Sets the transition matrix as uniform (equal probability of transitioning
            to all other possible states from each state) corresponding to the topology.

        Returns
        -------
        transitions: :class:`numpy:numpy.ndarray` (float)
            The uniform transition matrix of shape `(n_states, n_states)`.
        """
        transitions = np.zeros((self.n_states, self.n_states))
        for i, row in enumerate(transitions):
            size = min(2, self.n_states - i)
            row[i:(i + size)] = np.ones(size) / size
        return transitions

    def random_transitions(self) -> np.ndarray:
        """Sets the transition matrix as random (random probability of transitioning
        to all other possible states from each state) by sampling probabilities
        from a Dirichlet distribution, according to the topology.

        Returns
        -------
        transitions: :class:`numpy:numpy.ndarray` (float)
            The random transition matrix of shape `(n_states, n_states)`.
        """
        transitions = np.zeros((self.n_states, self.n_states))
        for i, row in enumerate(transitions):
            size = min(2, self.n_states - i)
            row[i:(i + size)] = self.random_state.dirichlet(np.ones(size))
        return transitions

    def check_transitions(self, transitions: np.ndarray) -> np.ndarray:
        """Validates a transition matrix according to the topology's restrictions.

        Parameters
        ----------
        transitions: numpy.ndarray (float)
            The transition matrix to validate.
        """
        super().check_transitions(transitions)
        if not np.allclose(transitions, np.diag(np.diag(transitions)) + np.diag(np.diag(transitions, k=1), k=1)):
            raise ValueError('Linear transition matrix must only consist of a diagonal and upper diagonal')
        return transitions

_topologies = {
    topology.name:topology
    for topology in (_ErgodicTopology, _LeftRightTopology, _LinearTopology)
}
