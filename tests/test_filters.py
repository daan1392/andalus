import pytest


@pytest.fixture
def test_assimilatin_suite():
    from andalus.assimilation import AssimilationSuite

    return AssimilationSuite.from_yaml("data/config.yaml")


class TestChi2Filter:
    def test_chi2_filter_pass(self, test_assimilatin_suite):
        """Test that a benchmark with chi-squared below the threshold passes."""
        from andalus.filters import Chi2Filter

        chi2_filter = Chi2Filter(threshold=10)
        assert bool(chi2_filter(test_assimilatin_suite.benchmarks["HMF001"]))

    def test_chi2_filter_fail(self, test_assimilatin_suite):
        """Test that a benchmark with chi-squared above the threshold fails."""
        from andalus.filters import Chi2Filter

        chi2_filter = Chi2Filter(threshold=0.0001)
        assert not bool(chi2_filter(test_assimilatin_suite.benchmarks["HMF001"]))


class TestChi2NuclearDataFilter:
    def test_chi2_nuclear_data_filter_pass(self, test_assimilatin_suite):
        """Test that a benchmark with chi-squared including nuclear data below the threshold passes."""
        from andalus.filters import Chi2NuclearDataFilter

        covariance_matrix = test_assimilatin_suite.covariances.matrix
        chi2_nd_filter = Chi2NuclearDataFilter(threshold=10, covariance_matrix=covariance_matrix)
        assert bool(chi2_nd_filter(test_assimilatin_suite.benchmarks["HMF001"]))

    def test_chi2_nuclear_data_filter_fail(self, test_assimilatin_suite):
        """Test that a benchmark with chi-squared including nuclear data above the threshold fails."""
        from andalus.filters import Chi2NuclearDataFilter

        covariance_matrix = test_assimilatin_suite.covariances.matrix
        chi2_nd_filter = Chi2NuclearDataFilter(threshold=0.0001, covariance_matrix=covariance_matrix)
        assert not bool(chi2_nd_filter(test_assimilatin_suite.benchmarks["HMF001"]))


class TestCompositeFilters:
    def test_and_operator(self, test_assimilatin_suite):
        """Test the logical AND (&) operator between filters."""
        from andalus.filters import Chi2Filter

        filter_pass = Chi2Filter(threshold=10)
        filter_fail = Chi2Filter(threshold=0.0001)

        and_filter_pass = filter_pass & filter_pass
        and_filter_fail = filter_pass & filter_fail

        assert bool(and_filter_pass(test_assimilatin_suite.benchmarks["HMF001"]))
        assert not bool(and_filter_fail(test_assimilatin_suite.benchmarks["HMF001"]))

    def test_or_operator(self, test_assimilatin_suite):
        """Test the logical OR (|) operator between filters."""
        from andalus.filters import Chi2Filter

        filter_pass = Chi2Filter(threshold=10)
        filter_fail = Chi2Filter(threshold=0.0001)

        or_filter_pass = filter_pass | filter_fail
        or_filter_fail = filter_fail | filter_fail

        assert bool(or_filter_pass(test_assimilatin_suite.benchmarks["HMF001"]))
        assert not bool(or_filter_fail(test_assimilatin_suite.benchmarks["HMF001"]))

    def test_not_operator(self, test_assimilatin_suite):
        """Test the logical NOT (~) operator on a filter."""
        from andalus.filters import Chi2Filter

        filter_pass = Chi2Filter(threshold=10)
        filter_fail = Chi2Filter(threshold=0.0001)

        not_filter_fail = ~filter_pass
        not_filter_pass = ~filter_fail

        assert not bool(not_filter_fail(test_assimilatin_suite.benchmarks["HMF001"]))
        assert bool(not_filter_pass(test_assimilatin_suite.benchmarks["HMF001"]))

    def test_complex_composition(self, test_assimilatin_suite):
        """Test complex composition of filters using multiple operators."""
        from andalus.filters import Chi2Filter

        filter_pass = Chi2Filter(threshold=10)
        filter_fail = Chi2Filter(threshold=0.0001)

        # (True | False) & ~(False) -> True & True -> True
        complex_filter_pass = (filter_pass | filter_fail) & (~filter_fail)
        assert bool(complex_filter_pass(test_assimilatin_suite.benchmarks["HMF001"]))

        # (True & False) | ~(True) -> False | False -> False
        complex_filter_fail = (filter_pass & filter_fail) | (~filter_pass)
        assert not bool(complex_filter_fail(test_assimilatin_suite.benchmarks["HMF001"]))
