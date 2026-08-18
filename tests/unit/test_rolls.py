from nqresearch.rolls import compute_front_series, expiry_sort_key


class TestExpirySortKey:
    def test_ordering(self):
        assert expiry_sort_key("NQU6") < expiry_sort_key("NQZ6")
        assert expiry_sort_key("NQZ5") < expiry_sort_key("NQH6")
        assert expiry_sort_key("NQZ26") == (2026, 11)
        assert expiry_sort_key("NQU5") == (2025, 8)


class TestFrontSeriesCausal:
    def test_first_session_unresolved_no_lookahead(self):
        r = compute_front_series({"2026-06-15": {"NQM6": 500_000}})
        assert r["per_session"][0]["front"] is None
        assert "UNRESOLVED_NO_PRIOR_SESSION" in r["per_session"][0]["flags"]

    def test_front_decided_from_previous_session_only(self):
        # Session S's own volume must NOT choose session S's contract:
        # NQU6 dominates on 06-17, but 06-17 still trades NQM6 (decided from
        # 06-16); the switch takes effect on 06-18.
        r = compute_front_series({
            "2026-06-15": {"NQM6": 500_000, "NQU6": 20_000},
            "2026-06-16": {"NQM6": 400_000, "NQU6": 90_000},
            "2026-06-17": {"NQM6": 150_000, "NQU6": 450_000},
            "2026-06-18": {"NQM6": 30_000, "NQU6": 600_000},
        })
        assert [x["front"] for x in r["per_session"]] == \
            [None, "NQM6", "NQM6", "NQU6"]
        assert r["switches"] == [{
            "session_id": "2026-06-18", "from": "NQM6", "to": "NQU6",
            "decided_from_session": "2026-06-17",
        }]

    def test_backward_spike_never_reverts(self):
        r = compute_front_series({
            "2026-06-16": {"NQM6": 100, "NQU6": 450},
            "2026-06-17": {"NQM6": 999, "NQU6": 400},
            "2026-06-18": {"NQM6": 10, "NQU6": 20},
        })
        # 06-17 front decided from 06-16 -> NQU6; 06-18 decided from 06-17
        # (NQM6 led, backward expiry) -> ignored, stays NQU6.
        assert [x["front"] for x in r["per_session"]] == [None, "NQU6", "NQU6"]
        assert "BACKWARD_VOLUME_LEADER_IGNORED" in r["per_session"][2]["flags"]
        assert r["switches"] == []

    def test_tie_retains_incumbent(self):
        r = compute_front_series({
            "2026-06-16": {"NQM6": 100, "NQU6": 50},
            "2026-06-17": {"NQM6": 70, "NQU6": 70},
            "2026-06-18": {"NQM6": 1, "NQU6": 1},
        })
        # 06-18 decided from 06-17's tie -> retains NQM6.
        assert r["per_session"][2]["front"] == "NQM6"
        assert r["switches"] == []

    def test_insufficient_volume_persists_front(self):
        r = compute_front_series({
            "2026-04-01": {"NQM6": 100},
            "2026-04-02": {"NQM6": 90},
            "2026-04-03": {},  # Good Friday: quotes only
            "2026-04-06": {"NQM6": 80},
        })
        fronts = [x["front"] for x in r["per_session"]]
        assert fronts == [None, "NQM6", "NQM6", "NQM6"]
        assert "INSUFFICIENT_VOLUME" in r["per_session"][3]["flags"]

    def test_no_incumbent_tie_prefers_earliest_expiry(self):
        r = compute_front_series({
            "2026-06-16": {"NQU6": 100, "NQM6": 100},
            "2026-06-17": {"NQU6": 1},
        })
        assert r["per_session"][1]["front"] == "NQM6"
