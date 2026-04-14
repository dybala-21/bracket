from bracket.probes import FilesystemProbe, ProbeRunner


class TestFilesystemProbe:
    def test_file_exists(self, tmp_path):
        p = tmp_path / "hello.txt"
        p.write_text("hello world")
        probe = FilesystemProbe(str(p), should_exist=True, contains="hello")
        result = probe.execute()
        assert result["passed"] is True

    def test_file_not_exists(self, tmp_path):
        probe = FilesystemProbe(str(tmp_path / "nonexistent.xyz"), should_exist=False)
        result = probe.execute()
        assert result["passed"] is True

    def test_file_missing_content(self, tmp_path):
        p = tmp_path / "foo.txt"
        p.write_text("foo bar")
        probe = FilesystemProbe(str(p), contains="baz")
        result = probe.execute()
        assert result["passed"] is False

    def test_bounded_read_does_not_load_full_file(self, tmp_path, monkeypatch):
        from bracket.probes import filesystem as fs_mod

        monkeypatch.setattr(fs_mod, "_MAX_READ_BYTES", 16)
        p = tmp_path / "big.txt"
        p.write_text("A" * 1000 + "needle")
        probe = FilesystemProbe(str(p), contains="needle")
        result = probe.execute()
        assert result["passed"] is False


class TestProbeRunner:
    def test_run_all(self, tmp_path):
        probe = FilesystemProbe(str(tmp_path / "nonexistent.xyz"), should_exist=False)
        runner = ProbeRunner()
        results = runner.run_all([probe])
        assert len(results) == 1
        assert results[0]["passed"] is True
