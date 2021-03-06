import collections
import functools

import numpy as np

from .. import optim
from .. import utils

from . import base


__all__ = ['FunkMF']


class FunkMF(base.Recommender):
    """Funk Matrix Factorization for recommender systems.

    The model equation is defined as:

    .. math::
        \\hat{y}(x) = \\langle \\mathbf{v}_u, \\mathbf{v}_i \\rangle = \\sum_{f=1}^{k} \\mathbf{v}_{u, f} \\cdot \\mathbf{v}_{i, f}

    Where :math:`k` is the number of latent factors. The model expect dict inputs containing both a
    ``user`` and an ``item`` entries.

    Parameters:
        n_factors (int): Dimensionality of the factorization or number of latent factors.
        optimizer (optim.Optimizer): The sequential optimizer used for updating the latent factors.
        loss (optim.Loss): The loss function to optimize for.
        l2 (float): Amount of L2 regularization used to push weights towards 0.
        initializer (optim.initializers.Initializer): Latent factors initialization scheme.
        clip_gradient (float): Clips the absolute value of each gradient value.
        random_state (int, ``numpy.random.RandomState`` instance or None): If int, ``random_state``
            is the seed used by the random number generator; if ``RandomState`` instance,
            ``random_state`` is the random number generator; if ``None``, the random number
            generator is the ``RandomState`` instance used by `numpy.random`.

    Attributes:
        u_latents (collections.defaultdict): The user latent vectors randomly initialized.
        i_latents (collections.defaultdict): The item latent vectors randomly initialized.
        u_optimizer (optim.Optimizer): The sequential optimizer used for updating the user latent
            weights.
        i_optimizer (optim.Optimizer): The sequential optimizer used for updating the item latent
            weights.

    Example:

        ::

            >>> from creme import optim
            >>> from creme import reco

            >>> X_y = (
            ...     ({'user': 'Alice', 'item': 'Superman'}, 8),
            ...     ({'user': 'Alice', 'item': 'Terminator'}, 9),
            ...     ({'user': 'Alice', 'item': 'Star Wars'}, 8),
            ...     ({'user': 'Alice', 'item': 'Notting Hill'}, 2),
            ...     ({'user': 'Alice', 'item': 'Harry Potter'}, 5),
            ...     ({'user': 'Bob', 'item': 'Superman'}, 8),
            ...     ({'user': 'Bob', 'item': 'Terminator'}, 9),
            ...     ({'user': 'Bob', 'item': 'Star Wars'}, 8),
            ...     ({'user': 'Bob', 'item': 'Notting Hill'}, 2)
            ... )

            >>> model = reco.FunkMF(
            ...     n_factors=10,
            ...     optimizer=optim.SGD(0.1),
            ...     initializer=optim.initializers.Normal(mu=0., sigma=0.1, random_state=11),
            ... )

            >>> for x, y in X_y:
            ...     _ = model.fit_one(x, y)

            >>> model.predict_one({'user': 'Bob', 'item': 'Harry Potter'})
            1.866272...

    Note:
        `reco.FunkMF` model expect a dict input with a ``user`` and an ``item`` entries without any
        type constraint on their values (i.e. can be strings or numbers). Other entries are
        ignored.

    References:
        1. `Netflix update: Try this at home <https://sifter.org/simon/journal/20061211.html>`_
        2. `Matrix factorization techniques for recommender systems <https://datajobs.com/data-science-repo/Recommender-Systems-[Netflix].pdf>`_

    """

    def __init__(self, n_factors=10, optimizer=None, loss=None, l2=0., initializer=None,
                 clip_gradient=1e12, random_state=None):
        self.n_factors = n_factors
        self.u_optimizer = optim.SGD() if optimizer is None else optimizer
        self.i_optimizer = optim.SGD() if optimizer is None else optimizer
        self.loss = optim.losses.Squared() if loss is None else loss
        self.l2 = l2

        if initializer is None:
            initializer = optim.initializers.Normal(mu=0., sigma=.1, random_state=random_state)
        self.initializer = initializer

        self.clip_gradient = clip_gradient
        self.random_state = random_state

        random_latents = functools.partial(
            self.initializer,
            shape=self.n_factors
        )
        self.u_latents = collections.defaultdict(random_latents)
        self.i_latents = collections.defaultdict(random_latents)

    def _predict_one(self, user, item):
        return np.dot(self.u_latents[user], self.i_latents[item])

    def _fit_one(self, user, item, y):

        # Calculate the gradient of the loss with respect to the prediction
        g_loss = self.loss.gradient(y, self._predict_one(user, item))

        # Clamp the gradient to avoid numerical instability
        g_loss = utils.math.clamp(g_loss, minimum=-self.clip_gradient, maximum=self.clip_gradient)

        # Calculate latent gradients
        u_latent_grad = {user: g_loss * self.i_latents[item] + self.l2 * self.u_latents[user]}
        i_latent_grad = {item: g_loss * self.u_latents[user] + self.l2 * self.i_latents[item]}

        # Update latent weights
        self.u_latents = self.u_optimizer.update_after_pred(self.u_latents, u_latent_grad)
        self.i_latents = self.i_optimizer.update_after_pred(self.i_latents, i_latent_grad)

        return self
