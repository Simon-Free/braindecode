# Authors: Simon Freyburger
#
# License: BSD-3

import torch
from functools import partial
import numpy as np
from torch.utils.data.dataset import Dataset
# Docstring, commentaires, flake8, authoring, extra indent
# required_variables, et le datum, args, kwargs
# TODO : pour les classes, one liner puis description plus complexe.
class Transform:
    """This is a framework that unifies transforms, so that they follow the
    structure used by most of the papers studying automatic data augmentation:
    a Transform is defined as an operation `t` applied with a magnitude `m`
    with probability `p`. Note that you can later compose Transforms using
    the Compose class of torchvision.

    Parameters
    ----------
    operation : Callable((Datum, int (optional)), Datum)
        A function taking a Datum object, and eventually a magnitude
        argument, and returning the transformed Datum. Omitting the
        `int` argument requires to set magnitude to None, and vice-versa.
    probability : int, optional
        The probability the function should be applied with, None if
        the operation is always applied.(default=None)
    magnitude : int, optional
        An amplitude parameter, define how much the transformation will
        alter the data, may be omitted if the transform does not need
        it (ex: reverse signal), (default=None)
    required_variables :
        dict(string:
                Callable((WindowsDataset or WindowsConcatDataset), any)),
        optional. A dictionary where keys are required variable name, and
        values are a function that computes this variable given an
        unaugmented dataset. (default={})
    """

    def __init__(self, operation, probability=None,
                 params={}, required_variables={}):
        self.probability = probability
        self.params = params
        if params:
            self.operation = partial(operation, params=params)
        else:
            self.operation = operation
        self.required_variables = required_variables

    def __call__(self, datum):
        """Apply the transform ``self.operation`` on the data X with
        probability ``self.probability`` and magnitude ``self.magnitude``

        Parameters
        ----------
        datum : Datum
            Data + metadata

        Returns
        -------
        Datum
            Transformed data + metadata
        """

        if self.probability is not None:
            rand_num = np.random.random()
            if rand_num >= self.probability:
                return datum
        return self.operation(datum)


class AugmentedDataset(Dataset):
    """An overlay (not a subclass though) to apply on a basic WindowsDataset
    or BaseConcatDataset or a Subset of one of these two classes. Follows the
    canonical way to augment data of Pytorch (see [this article]
    (https://pytorch.org/tutorials/beginner/data_loading_tutorial.html) for
    more informations.) Main point is, if you pass a list of `n` transforms and
    a dataset of size `s`, you will obtain a dataset of size `n x s`. Note that
    transforms are reapplied every time the `__getitem__` function is called,
    so if you have some randomness in it, you will obtain different transformed
    data at every epoch. Note that you can compose transforms using the Compose
    class of torchvision.

    Parameters
    ----------
    ds : WindowsDataset or BaseConcatDataset or a Subset of one of those.
        The unaugmented dataset
    list_of_transforms :
        list(Transform or torchvision.transforms.Compose(Transform)),
        optional. A list of transforms that will be applied to data, by
        default identity (default=[Transform(lambda datum:datum)]).
    """

    def __init__(self, ds,
                 list_of_transforms=[
                     Transform(lambda datum:datum)]) -> None:
        # Initialize the augmented dataset, and computes required
        # variables for applying transforms
        self.list_of_transforms = list_of_transforms
        self.ds = ds
        self.required_variables = {}
        self.list_of_labels = \
            list(set([elem[1] for elem in iter(self.ds)]))
        self.list_of_labels.sort()
        self.__initialize_required_variables()

    def __len__(self):
        return(len(self.ds) * len(self.list_of_transforms))

    def __getitem__(self, index):
        # First get the indexes of the transform and of the unaugmented data
        tf_index = index % len(self.list_of_transforms)
        img_index = index // len(self.list_of_transforms)

        # Get the unaugmented data
        X, y, crops_ind = self.ds[img_index]
        y = tuple([int(elem == y)
                   for elem in self.list_of_labels])

        class Datum:
            def __init__(self, X, y, crops_ind, ds,
                         required_variables, list_of_labels):
                self.X = X 
                self.y = y
                self.crops_ind = crops_ind
                self.ds = ds
                self.required_variables = required_variables
                self.list_of_labels = list_of_labels
        # Initialize Datum object with metadata required to compute transforms,
        # then compute the transform.
        transf_datum = self.list_of_transforms[tf_index](
            Datum(X, y, crops_ind, self.ds, self.required_variables,
                  self.list_of_labels))
        # Returns augmented data.
        X, y, crops_ind = transf_datum.X, transf_datum.y, transf_datum.crops_ind

        return X, y, crops_ind

    def __initialize_required_variables(self):

        for transform in self.list_of_transforms:
            for key in transform.required_variables.keys():
                self.required_variables[key] = \
                    transform.required_variables[key](
                        self.ds, self.list_of_transforms)


class mixup_iterator(torch.utils.data.DataLoader):
    """Implements Iterator for Mixup for EEG data. See [mixup].
    Code adapted from
    # TODO ref sbbrandt + rewrite docstring
    Parameters
    ----------
    dataset: Dataset
        dataset from which to load the data.
    alpha: float
        mixup hyperparameter.
    beta_per_sample: bool (default=False)
        by default, one mixing coefficient per batch is drawn from an beta
        distribution. If True, one mixing coefficient per sample is drawn.
    References
    ----------
    ..  [mixup] Hongyi Zhang, Moustapha Cisse, Yann N. Dauphin, David Lopez-Paz
        mixup: Beyond Empirical Risk Minimization
        Online: https://arxiv.org/abs/1710.09412
    """

    def __init__(self, dataset, **kwargs):
        super().__init__(dataset, collate_fn=self.mixup, **kwargs)
        self.n_labels = len(dataset.list_of_labels)
        self.ismixed = True

    def mixup(self, data):

        batch_size = len(data)
        n_channels, n_times = data[0][0].shape
        batch_X = np.zeros((batch_size, n_channels, n_times))
        batch_y = np.zeros((batch_size, self.n_labels))
        batch_crop_inds = np.zeros((batch_size, 3))
        for idx in range(batch_size):
            batch_X[idx] = data[idx][0]
            if len(data[idx][1]) > 1:
                # Training
                batch_y[idx] = data[idx][1]
            else:
                # Prediction
                batch_y[idx, data[idx][1]] = 1
            batch_crop_inds[idx] = np.array(data[idx][2])
        batch_X = torch.tensor(batch_X).type(torch.float32)
        batch_y = torch.tensor(batch_y).type(torch.float32)
        batch_crop_inds = torch.tensor(batch_crop_inds).type(torch.int64)

        return batch_X, batch_y, batch_crop_inds


class general_mixup_criterion:
    # TODO : probleme dans les labels.
    def __init__(self, loss=torch.nn.functional.nll_loss):
        self.loss = loss

    def __call__(self, preds, target):
        return self.loss_function(preds, target)

    def loss_function(self, preds, target):
        ret = None
        if len(target.shape) > 1:
            for i in range(target.shape[1]):
                prop = target[:, i]
                label = torch.Tensor(
                    np.full(
                        target.shape[0],
                        i)).type(
                    torch.LongTensor)
                loss_val = self.loss(preds, label, reduction='none')
                if ret is None:
                    ret = torch.mul(prop, loss_val)
                else:
                    ret += torch.mul(prop, loss_val)
            return ret.mean()
        else:
            return(self.loss(preds, target, reduction='mean'))


class Compose:
    """Composes several transforms together.

        Parameters
        ----------
        transforms: list(Transform)
            list of transforms to compose.
    """

    def __init__(self, transforms):
        self.transforms = transforms

    def __call__(self, datum):
        for t in self.transforms:
            datum = t(datum)
        return datum
