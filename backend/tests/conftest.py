import pytest

from app.rag.procedure_profiles import OSCAT_SCT_TOSCANA_PROFILE


@pytest.fixture
def oscat_profile():
    return (OSCAT_SCT_TOSCANA_PROFILE,)


@pytest.fixture
def oscat_profile_ids():
    return ("oscat_sct_toscana",)
