# Authors: Simon Freyburger
#
# License: BSD-3

from braindecode.augmentation.transforms.masking_along_axis import \
    mask_along_frequency, mask_along_time
import torch
from skorch.callbacks import LRScheduler
from braindecode import EEGClassifier
from braindecode.util import set_random_seeds
from braindecode.models import SleepStagerChambon2018
from braindecode.datasets.sleep_physionet import get_dummy_sample
from braindecode.augmentation.transform_class import Transform
from braindecode.augmentation.transforms.identity import identity
from braindecode.datasets.base import AugmentedDataset
import numpy as np


def test_dummy_augmented_training():
    train_sample, _, _ = get_dummy_sample()
    model_args = {"n_classes": len(set(
        [train_sample[i][1] for i in range(len(train_sample))])),
        "n_chans": int(train_sample[0][0].shape[0]),
        "input_window_samples": int(train_sample[0][0].shape[1]),
        "model_type": "SleepStager",
        "batch_size": 256,
        "seed": None,
        "sfreq": 100,
        "lr": 0.002,
        "weight_decay": 0,
        "n_epochs": 50,
        "n_cross_val": 3,
        "criterion": torch.nn.CrossEntropyLoss,
        "device": "cuda:2",
    }
    cuda = torch.cuda.is_available()
    device = model_args["device"] if cuda else 'cpu'
    if cuda:
        torch.backends.cudnn.benchmark = True
    set_random_seeds(0, cuda=cuda)
    nn_architecture = SleepStagerChambon2018(
        n_channels=model_args["n_chans"],
        sfreq=model_args["sfreq"],
        n_classes=model_args["n_classes"] + 1,
        input_size_s=model_args["input_window_samples"] /
        model_args["sfreq"],
    )

    if cuda:
        nn_architecture.cuda()

    clf = EEGClassifier(
        nn_architecture,
        criterion=model_args["criterion"],
        optimizer=torch.optim.AdamW,
        optimizer__lr=model_args["lr"],
        optimizer__weight_decay=model_args["weight_decay"],
        batch_size=model_args["batch_size"],
        train_split=None,
        callbacks=[
            "accuracy",
            ("lr_scheduler",
             LRScheduler('CosineAnnealingLR',
                         T_max=model_args["n_epochs"] - 1))
        ],
        device=device,
        iterator_train__num_workers=20,
        iterator_train__pin_memory=True
    )  # torch.in torch.out

    subpolicies_list = [
        Transform(identity),
        Transform(mask_along_frequency),
        Transform(mask_along_time)]

    train_sample = AugmentedDataset(train_sample, subpolicies_list)
    y_train = np.array([data[1] for data in iter(train_sample)])

    clf.fit(train_sample, y=y_train, epochs=model_args["n_epochs"])

    return clf