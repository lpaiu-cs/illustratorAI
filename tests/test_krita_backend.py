from pathlib import Path


class FakeSession:
    """Stands in for KritaSession: records the shared export path's calls."""

    def __init__(self):
        self.exports = []

    def export_document(self, document, path):
        self.exports.append(Path(path))
        Path(path).write_bytes(b"png")


def make_backend(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "pykrita"))
    from nic_agent_bridge.krita_backend import KritaBackend

    backend = KritaBackend(FakeSession(), output_root=tmp_path)
    backend.document = object()  # any direct Document.exportImage call would fail here
    return backend


def test_export_paths_use_session_export_document(tmp_path, monkeypatch):
    backend = make_backend(tmp_path, monkeypatch)

    backend.op_export_png({"file_name": "out.png"})
    assert backend.session.exports == [tmp_path / "out.png"]

    assert backend.canvas_png_base64() == "cG5n"  # base64 of b"png"
    assert len(backend.session.exports) == 2
