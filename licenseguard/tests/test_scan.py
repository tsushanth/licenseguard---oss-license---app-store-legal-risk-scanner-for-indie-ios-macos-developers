import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import scan  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")


class TestParsers(unittest.TestCase):
    def test_parse_spm_resolved(self):
        deps = scan.parse_spm_resolved(os.path.join(SAMPLES, "Package.resolved"))
        names = dict(deps)
        self.assertEqual(names["alamofire"], "5.9.1")
        self.assertEqual(names["kingfisher"], "7.11.0")
        self.assertEqual(names["ffmpegkit"], "6.0")
        self.assertEqual(names["exampleagplsynckit"], "2.1.0")
        self.assertEqual(names["some-unlisted-utility"], "0.3.0")
        self.assertEqual(len(deps), 6)

    def test_parse_podfile_lock(self):
        deps = scan.parse_podfile_lock(os.path.join(SAMPLES, "Podfile.lock"))
        names = dict(deps)
        self.assertEqual(names["Alamofire"], "5.9.1")
        self.assertEqual(names["SnapKit"], "5.7.1")
        self.assertEqual(names["MobileVLCKit"], "3.5.1")
        self.assertEqual(names["x264"], "0.164.3101")
        # nested subspec line ("SDWebImage/Core (= 5.19.4)") must not be
        # picked up as its own top-level dependency
        self.assertNotIn("SDWebImage/Core", names)
        self.assertEqual(names["SDWebImage"], "5.19.4")
        self.assertEqual(len(deps), 5)

    def test_parse_cartfile_resolved(self):
        deps = scan.parse_cartfile_resolved(os.path.join(SAMPLES, "Cartfile.resolved"))
        names = dict(deps)
        self.assertEqual(names["Alamofire"], "5.9.1")
        self.assertEqual(names["lottie-ios"], "4.4.3")
        self.assertEqual(names["ffmpeg-kit"], "6.0")
        self.assertEqual(len(deps), 5)


class TestClassification(unittest.TestCase):
    def setUp(self):
        self.license_db = scan.load_json(scan.DEFAULT_LICENSE_DB)
        self.license_rules = scan.load_json(scan.DEFAULT_LICENSE_RULES)

    def classify(self, name, version="1.0.0"):
        return scan.classify(name, version, self.license_db, self.license_rules)

    def test_permissive_package(self):
        result = self.classify("Alamofire")
        self.assertEqual(result["license"], "MIT")
        self.assertEqual(result["risk"], "permissive")
        self.assertFalse(result["blocks_app_store"])

    def test_weak_copyleft_package(self):
        result = self.classify("MobileVLCKit")
        self.assertEqual(result["license"], "LGPL-2.1")
        self.assertEqual(result["risk"], "weak-copyleft")
        self.assertFalse(result["blocks_app_store"])
        self.assertIn("relink", result["explanation"])

    def test_gpl_package_is_blocking(self):
        result = self.classify("x264")
        self.assertEqual(result["license"], "GPL-2.0")
        self.assertEqual(result["risk"], "copyleft")
        self.assertTrue(result["blocks_app_store"])
        self.assertIn("Apple", result["explanation"])

    def test_agpl_package_is_blocking(self):
        result = self.classify("ExampleAGPLSyncKit")
        self.assertEqual(result["license"], "AGPL-3.0")
        self.assertEqual(result["risk"], "network-copyleft")
        self.assertTrue(result["blocks_app_store"])

    def test_unknown_package(self):
        result = self.classify("some-unlisted-utility")
        self.assertEqual(result["license"], "Unknown")
        self.assertEqual(result["risk"], "unknown")


class TestAttribution(unittest.TestCase):
    def setUp(self):
        license_db = scan.load_json(scan.DEFAULT_LICENSE_DB)
        license_rules = scan.load_json(scan.DEFAULT_LICENSE_RULES)
        deps = [
            ("Alamofire", "5.9.1"),
            ("SnapKit", "5.7.1"),
            ("x264", "0.164.3101"),
            ("ExampleAGPLSyncKit", "2.1.0"),
        ]
        self.classified = [scan.classify(n, v, license_db, license_rules) for n, v in deps]

    def test_attribution_includes_permissive_deps(self):
        attribution = scan.generate_attribution(self.classified)
        self.assertIn("Alamofire", attribution)
        self.assertIn("SnapKit", attribution)

    def test_attribution_excludes_blocking_deps(self):
        attribution = scan.generate_attribution(self.classified)
        lines_before_comment = attribution.split("<!--")[0]
        self.assertNotIn("x264", lines_before_comment)
        self.assertNotIn("ExampleAGPLSyncKit", lines_before_comment)
        # still called out separately so they aren't silently dropped
        self.assertIn("x264", attribution)
        self.assertIn("ExampleAGPLSyncKit", attribution)


class TestReport(unittest.TestCase):
    def test_report_flags_gpl_with_explanation(self):
        license_db = scan.load_json(scan.DEFAULT_LICENSE_DB)
        license_rules = scan.load_json(scan.DEFAULT_LICENSE_RULES)
        classified = [scan.classify("x264", "0.164.3101", license_db, license_rules)]
        report = scan.generate_report("Podfile.lock", "cocoapods", classified)
        self.assertIn("BLOCKS App Store distribution", report)
        self.assertIn("Apple", report)


if __name__ == "__main__":
    unittest.main()
