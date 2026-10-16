from curve_activity import CurveActivity

def test_counts_and_window():
    a = CurveActivity(window_seconds=60)
    assert a.record({'mint':'abc', 'txType':'buy', 'solAmount':1.25}, now=100)
    assert a.record({'mint':'abc', 'txType':'sell', 'solAmount':.5}, now=110)
    assert a.summary('abc', now=120) == {'trades':2,'buys':1,'sells':1,'volume_sol':1.75}
    assert a.summary('abc', now=171)['trades'] == 0

def test_reject_bad_events():
    a = CurveActivity()
    for event in ({}, {'mint':'x','txType':'create','solAmount':1}, {'mint':'x','txType':'buy','solAmount':-1}, {'mint':'x','txType':'buy','solAmount':'oops'}):
        assert not a.record(event)

def test_bounded():
    a = CurveActivity(max_mints=1)
    a.record({'mint':'a','txType':'buy','solAmount':1}, now=10)
    a.record({'mint':'b','txType':'buy','solAmount':2}, now=10)
    assert a.summary('a', now=10)['trades'] == 0
    assert a.summary('b', now=10)['trades'] == 1
