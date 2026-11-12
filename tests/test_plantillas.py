import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402
import plantillas  # noqa: E402

GOOD = {"format": "nova-profile", "format_version": 1, "name": "PvP", "version": "1.21.1", "loader": "fabric",
        "loader_version": "0.16.9", "memory": 4, "jvm_args": "-XX:+UseG1GC", "resolution": "1920x1080",
        "notes": "hola", "mods": [{"id": "sodium", "name": "Sodium", "version": "0.6"}]}


class TemplateTests(unittest.TestCase):
    def test_every_template_is_valid(self):
        self.assertEqual(len(plantillas.TEMPLATES), 7)
        for key, template in plantillas.TEMPLATES.items():
            with self.subTest(key=key):
                settings = plantillas.apply_template(key)
                self.assertIn(settings["loader"], motor.LOADERS)
                self.assertTrue(1 <= settings["memory"] <= 64)
                motor.parse_jvm_args(settings["jvm_args"])
                self.assertTrue(template["title"] and template["detail"])

    def test_memory_is_capped_to_half_of_the_ram(self):
        self.assertEqual(plantillas.apply_template("modpacks", ram_mb=8192)["memory"], 4)
        self.assertEqual(plantillas.apply_template("modpacks", ram_mb=4096)["memory"], 2)
        self.assertEqual(plantillas.apply_template("modpacks", ram_mb=1024)["memory"], 1)
        self.assertEqual(plantillas.apply_template("modpacks", ram_mb=65536)["memory"], 6)
        self.assertEqual(plantillas.apply_template("modpacks")["memory"], 6)

    def test_unknown_template(self):
        with self.assertRaises(ValueError):
            plantillas.apply_template("nope")


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, data, name="p.json"):
        path = self.dir / name
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def test_round_trip_and_java_path_is_never_exported(self):
        instance = {"name": "X", "version": "1.21.1", "loader": "fabric", "loader_version": "0.16.9", "memory": 6,
                    "jvm_args": "-XX:+UseG1GC", "java": "/home/user/jdk/bin/java", "resolution": "default"}
        exported = plantillas.export_profile(instance, mods=[("sodium", "Sodium", "0.6")])
        self.assertNotIn("java", exported)
        self.assertNotIn("/home/user", json.dumps(exported))
        profile = plantillas.read_profile(self.write(exported))
        self.assertEqual((profile["version"], profile["loader"], profile["memory"]), ("1.21.1", "fabric", 6))
        self.assertEqual(profile["mods"], [{"id": "sodium", "name": "Sodium", "version": "0.6"}])

    def test_describe_lists_what_will_be_applied(self):
        lines = plantillas.describe_profile(plantillas.read_profile(self.write(GOOD)))
        text = "\n".join(lines)
        self.assertIn("Minecraft 1.21.1 · Fabric 0.16.9", text)
        self.assertIn("RAM: 4 GB", text)
        self.assertIn("no se instalan automáticamente", text)

    def test_rejects_bad_files(self):
        cases = {
            "no json": "{nope",
            "list": "[]",
            "wrong mark": {**GOOD, "format": "other"},
            "future version": {**GOOD, "format_version": 9},
            "bad loader": {**GOOD, "loader": "magic"},
            "bad version": {**GOOD, "version": "../../etc"},
            "bad memory": {**GOOD, "memory": 999},
            "bool memory": {**GOOD, "memory": True},
            "bad jvm": {**GOOD, "jvm_args": "-Xmx64G"},
            "agent": {**GOOD, "jvm_args": "-javaagent:/tmp/x.jar"},
            "long notes": {**GOOD, "notes": "x" * 500},
            "name type": {**GOOD, "name": 5},
            "bad loader version": {**GOOD, "loader_version": "a b;c"},
        }
        for label, data in cases.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                plantillas.read_profile(self.write(data))

    def test_huge_or_missing_file(self):
        with self.assertRaises(ValueError):
            plantillas.read_profile(self.write("x" * (plantillas.MAX_PROFILE_BYTES + 1)))
        with self.assertRaises(ValueError):
            plantillas.read_profile(self.dir / "nope.json")

    def test_unknown_resolution_falls_back_and_bad_mods_are_dropped(self):
        profile = plantillas.read_profile(self.write({**GOOD, "resolution": "1x1", "mods": ["x", {"id": 3}, {"id": "a"}]}))
        self.assertEqual(profile["resolution"], "default")
        self.assertEqual(profile["mods"], [{"id": "a", "name": "", "version": ""}])


if __name__ == "__main__":
    unittest.main()
