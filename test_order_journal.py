import pytest
from order_journal import Journal, JournalError

def test_intent_persists_and_blocks_duplicate(tmp_path):
    j = Journal(str(tmp_path / 'orders'))
    entry = j.create_intent(action='buy', mint='example-mint', usd=2)
    assert Journal(str(tmp_path / 'orders')).status()['unresolved'] == 1
    assert entry['status'] == 'intent'
    with pytest.raises(JournalError): j.create_intent(action='buy', mint='example-mint', usd=2)

def test_cap(tmp_path):
    j = Journal(str(tmp_path / 'orders'))
    with pytest.raises(JournalError): j.create_intent(action='buy', mint='example-mint', usd=11)

def test_corrupt_fails_closed(tmp_path):
    d = tmp_path / 'orders'; d.mkdir(); (d / 'bad.json').write_text('{')
    with pytest.raises(JournalError): Journal(str(d)).assert_no_unresolved()
