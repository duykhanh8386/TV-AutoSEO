import ast
import importlib
import pathlib
import unittest

import app as app_entry
from src import license_manager, paths, runtime_instance
from src.route_manager import router


ROOT = pathlib.Path(__file__).resolve().parent.parent
DISALLOWED_MODULES = (
    "src.audio_recovery",
    "src.audio_batch_matcher",
    "src.video_loop_transition",
    "src.youtube_caption_api",
    "web.components.auto_registry",
    "faster_whisper",
)


class TVAutoSEOBoundaryTests(unittest.TestCase):
    def test_isolated_namespace_and_ports_do_not_collide_with_tuat_videos(self):
        self.assertNotEqual(paths.APP_NAMESPACE_ID, "7F47B95D-6FD8-4A87-B2F8-9B0CE6A91D42")
        self.assertTrue(paths.APP_DATA_NAMESPACE.startswith("TVAutoSEO-"))
        self.assertEqual(runtime_instance.APP_PORT_START, 18101)
        self.assertEqual(runtime_instance.APP_PORT_END, 18120)
        self.assertTrue(
            set(range(runtime_instance.APP_PORT_START, runtime_instance.APP_PORT_END + 1)).isdisjoint(
                set(range(18081, 18101))
            )
        )
        self.assertIn("TVAutoSEO-", runtime_instance._MUTEX_NAME)
        self.assertTrue(runtime_instance.RUNTIME_HEALTH_PATH.startswith("/__tvautoseo_"))

    def test_shared_keygen_product_and_fingerprint_preserved(self):
        self.assertEqual(license_manager.KEYGEN_ACCOUNT_ID, "fe587f43-390a-4e00-a8b2-0c69d2f3629c")
        self.assertEqual(license_manager.KEYGEN_PRODUCT_ID, "f30b2ff1-6393-418a-8473-6ddf46eb227f")
        self.assertEqual(license_manager.KEYGEN_POLICY_ID, "a4ab8481-7144-4ba2-92a0-9e854544eb67")
        fingerprint_source = pathlib.Path(license_manager.__file__).read_text(encoding="utf-8")
        self.assertIn('f"tv-automation:{source}"', fingerprint_source)

    def test_only_expected_routes_are_registered(self):
        importlib.import_module("web.views")
        self.assertEqual(set(router.routes.keys()), {"/auth", "/studio", "/videos/publishing"})
        self.assertTrue(callable(app_entry.main))

    def test_runtime_sources_have_no_removed_feature_imports(self):
        targets = [ROOT / "app.py"]
        targets.extend(sorted((ROOT / "src").rglob("*.py")))
        targets.extend(sorted((ROOT / "web").rglob("*.py")))
        for file_path in targets:
            tree = ast.parse(file_path.read_text(encoding="utf-8-sig"), filename=str(file_path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for mod in names:
                    for banned in DISALLOWED_MODULES:
                        self.assertFalse(
                            mod == banned or mod.startswith(banned + "."),
                            f"Disallowed import {mod!r} found in {file_path}",
                        )


if __name__ == "__main__":
    unittest.main()
