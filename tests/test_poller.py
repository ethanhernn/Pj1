from src.notify import PRIORITY_DEFAULT, PRIORITY_HIGH, PRIORITY_URGENT
from src.poller import find_new_filings, parse_submissions


def test_parses_parallel_arrays(submissions):
    filings = parse_submissions(submissions, cik_int=2045724)
    assert len(filings) == 4
    assert filings[0].accession_number == "0002045724-26-000012"
    assert filings[0].form == "13F-HR"


def test_index_url_format(submissions):
    f = parse_submissions(submissions, cik_int=2045724)[0]
    assert f.index_url == (
        "https://www.sec.gov/Archives/edgar/data/2045724/"
        "000204572426000012/0002045724-26-000012-index.htm"
    )


def test_priority_classification(submissions):
    filings = {f.form: f for f in parse_submissions(submissions, cik_int=2045724)}
    assert filings["13F-HR"].priority == PRIORITY_HIGH
    assert filings["SC 13D"].priority == PRIORITY_URGENT
    assert filings["13F-NT"].priority == PRIORITY_DEFAULT


def test_acceptance_seed_all_but_latest_yields_one(submissions):
    """Layer 1 acceptance test: seed all but the most recent filing, expect
    exactly one new filing with a working link."""
    filings = parse_submissions(submissions, cik_int=2045724)
    all_acc = {f.accession_number for f in filings}
    latest = filings[0].accession_number  # submissions index is newest-first
    seen = all_acc - {latest}

    new = find_new_filings(filings, seen)
    assert len(new) == 1
    assert new[0].accession_number == latest
    assert new[0].index_url.startswith("https://www.sec.gov/Archives/edgar/data/")


def test_new_filings_ordered_oldest_first(submissions):
    filings = parse_submissions(submissions, cik_int=2045724)
    new = find_new_filings(filings, seen=set())
    dates = [f.filing_date for f in new]
    assert dates == sorted(dates)  # oldest first
