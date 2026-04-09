from tools.register_validator import RunCounters, filter_outliers_with_counter


def test_run_counters_defaults_to_zero():
    c = RunCounters()
    assert c.fin_extracted == 0
    assert c.prob_extracted == 0
    assert c.fin_after_iqr_filter == 0
    assert c.prob_after_iqr_filter == 0
    assert c.outliers_removed == 0


def test_filter_outliers_with_counter_increments_removed():
    c = RunCounters()
    # 5 values — one obvious outlier
    filtered = filter_outliers_with_counter([10.0, 11.0, 12.0, 13.0, 999.0], c, dim="fin")
    assert c.fin_extracted == 5
    assert c.fin_after_iqr_filter == len(filtered)
    assert c.outliers_removed == 5 - len(filtered)


def test_filter_outliers_with_counter_fewer_than_4_no_filter():
    c = RunCounters()
    filtered = filter_outliers_with_counter([10.0, 11.0, 12.0], c, dim="prob")
    assert filtered == [10.0, 11.0, 12.0]
    assert c.prob_extracted == 3
    assert c.prob_after_iqr_filter == 3
    assert c.outliers_removed == 0


def test_counters_track_queried_and_matched_sets():
    c = RunCounters()
    # simulate: 3 unique source IDs queried, 2 yielded results
    c.queried_source_ids.update({"verizon-dbir", "ibm-cost-data-breach", "enisa-threat-landscape"})
    c.matched_source_ids.update({"verizon-dbir", "ibm-cost-data-breach"})
    assert len(c.queried_source_ids) == 3
    assert len(c.matched_source_ids) == 2
    assert c.matched_source_ids.issubset(c.queried_source_ids)
