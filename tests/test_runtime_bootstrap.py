"""
Unit tests for managed uv/Python runtime bootstrap helpers.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src import runtime_bootstrap


class TestRuntimeBootstrap(unittest.TestCase):
    """
    Verifies uv asset selection and orchestration without network access.
    """

    def test_uv_download_spec_windows_x86_64(self) -> None:
        """
        Ensures Windows x86_64 maps to the msvc zip asset.
        """

        with (
            patch.object(runtime_bootstrap.sys, "platform", "win32"),
            patch.object(runtime_bootstrap, "_machine_tag", return_value="x86_64"),
        ):
            filename, url = runtime_bootstrap.uv_download_spec()
        self.assertTrue(filename.endswith(".zip"))
        self.assertIn("x86_64-pc-windows-msvc", filename)
        self.assertIn(runtime_bootstrap.UV_VERSION, url)

    def test_uv_download_spec_linux_x86_64(self) -> None:
        """
        Ensures Linux x86_64 maps to the gnu tarball asset.
        """

        with (
            patch.object(runtime_bootstrap.sys, "platform", "linux"),
            patch.object(runtime_bootstrap, "_machine_tag", return_value="x86_64"),
        ):
            filename, url = runtime_bootstrap.uv_download_spec()
        self.assertTrue(filename.endswith(".tar.gz"))
        self.assertIn("x86_64-unknown-linux-gnu", filename)
        self.assertIn(runtime_bootstrap.UV_VERSION, url)

    def test_uv_download_spec_rejects_unsupported(self) -> None:
        """
        Ensures unsupported platforms raise a clear error.
        """

        with patch.object(runtime_bootstrap.sys, "platform", "darwin"):
            with self.assertRaises(RuntimeError):
                runtime_bootstrap.uv_download_spec()

    def test_ensure_uv_reuses_existing_binary(self) -> None:
        """
        Ensures an existing project-local uv binary is not re-downloaded.
        """

        project = Path("/tmp/snappix-runtime-test")
        uv_path = project / ".snappix-runtime" / "uv" / (
            "uv.exe" if sys.platform == "win32" else "uv"
        )
        with (
            patch.object(runtime_bootstrap, "uv_binary_path", return_value=uv_path),
            patch.object(Path, "is_file", return_value=True),
            patch.object(runtime_bootstrap, "_download_file") as download_mock,
        ):
            result = runtime_bootstrap.ensure_uv(project)
        self.assertEqual(result, uv_path)
        download_mock.assert_not_called()

    def test_bootstrap_managed_runtime_success(self) -> None:
        """
        Ensures orchestration installs requirements through uv helpers.
        """

        project = Path("/tmp/snappix-runtime-test")
        with (
            patch.object(runtime_bootstrap, "ensure_uv", return_value=Path("/tmp/uv")),
            patch.object(runtime_bootstrap, "install_requirements") as install_mock,
        ):
            code = runtime_bootstrap.bootstrap_managed_runtime(project)
        self.assertEqual(code, 0)
        install_mock.assert_called_once()

    def test_bootstrap_managed_runtime_failure(self) -> None:
        """
        Ensures RuntimeError from uv provisioning becomes exit code 1.
        """

        project = Path("/tmp/snappix-runtime-test")
        with patch.object(
            runtime_bootstrap,
            "ensure_uv",
            side_effect=RuntimeError("network down"),
        ):
            code = runtime_bootstrap.bootstrap_managed_runtime(project)
        self.assertEqual(code, 1)

    def test_find_extracted_uv_nested(self) -> None:
        """
        Ensures uv is discovered inside versioned extract folders.
        """

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "uv-x86_64-unknown-linux-gnu" / "uv"
            nested.parent.mkdir(parents=True)
            nested.write_text("", encoding="utf-8")
            found = runtime_bootstrap._find_extracted_uv(root)
        self.assertEqual(found, nested)


if __name__ == "__main__":
    unittest.main()
