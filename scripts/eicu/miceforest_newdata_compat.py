# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Local adapter for observed miceforest6.0.5 new-data iteration counter bug.

The installed package is not changed. Kernel training is unaffected. The adapter
is scoped to creation of new-data ImputedData objects, whose setter otherwise
stores each iteration without advancing iteration_tab. Without the repair,
subsequent chained iterations and complete_data(-1) reuse initialization.
"""
from contextlib import contextmanager
from importlib import import_module
from miceforest.imputed_data import ImputedData


class TrackedNewData(ImputedData):
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        variable, iteration, dataset = key
        # max also makes this safe if a future setter starts tracking itself.
        self.iteration_tab[variable, dataset] = max(
            self.iteration_tab[variable, dataset], iteration)


@contextmanager
def tracked_newdata_constructor():
    module = import_module("miceforest.imputation_kernel")
    original = module.ImputedData
    module.ImputedData = TrackedNewData
    try:
        yield
    finally:
        module.ImputedData = original


def impute_new_data_checked(kernel, data, *, iterations, **kwargs):
    with tracked_newdata_constructor():
        result = kernel.impute_new_data(data.copy(deep=True), iterations=iterations, **kwargs)
    for feature in data.columns[data.isna().any()]:
        assert result.iteration_count(dataset=0, variable=feature) == iterations, feature
    final_explicit = result.complete_data(dataset=0, iteration=iterations)
    final_default = result.complete_data(dataset=0)
    assert final_default.equals(final_explicit), "Default completion is not final iteration"
    return result
