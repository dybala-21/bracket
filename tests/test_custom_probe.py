from bracket.probes import CustomProbe


class TestCustomProbe:
    def test_passing(self):
        probe = CustomProbe(
            name="check_config",
            check=lambda: {"passed": True, "detail": "config ok"},
        )
        result = probe.execute()
        assert result["passed"] is True
        assert result["probe_name"] == "check_config"

    def test_failing(self):
        probe = CustomProbe(
            name="check_db",
            check=lambda: {"passed": False, "detail": "db unreachable"},
        )
        result = probe.execute()
        assert result["passed"] is False

    def test_exception_handled(self):
        def bad_check():
            raise RuntimeError("boom")

        probe = CustomProbe(name="bad", check=bad_check)
        result = probe.execute()
        assert result["passed"] is False
        assert "boom" in result["detail"]

    def test_auto_fills_probe_name(self):
        probe = CustomProbe(
            name="auto",
            check=lambda: {"passed": True, "detail": "ok"},
        )
        result = probe.execute()
        assert result["probe_name"] == "auto"
