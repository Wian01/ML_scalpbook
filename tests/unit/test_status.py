from nqresearch.qa.status import FAIL, PASS, WARN, check, worst


class TestWorst:
    def test_empty_is_pass(self):
        assert worst([]) == PASS

    def test_ordering(self):
        assert worst([PASS, PASS]) == PASS
        assert worst([PASS, WARN]) == WARN
        assert worst([WARN, FAIL, PASS]) == FAIL


class TestCheck:
    def test_shape(self):
        c = check("x", PASS, "ok", extra=1)
        assert c == {"check": "x", "status": PASS, "detail": "ok", "extra": 1}
