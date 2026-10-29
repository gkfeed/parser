from contextlib import ExitStack

import pytest

from tests.browser.resources import LocalChromium, local_site


@pytest.fixture
def site():
    with local_site() as site:
        yield site


@pytest.fixture
def browser(site):
    # Keep the HTTP dependency alive until browser and profile cleanup finishes.
    with ExitStack() as resources:
        yield LocalChromium(resources)
