import unittest

import lanzamiento as lz


class StageTests(unittest.TestCase):
    def test_messages_map_to_steps(self):
        cases = (("Preparando Minecraft…", 0), ("Verificando la cuenta de Microsoft…", 0),
                 ("Descargando Minecraft 1.21.11…", 1), ("Descargando recursos de Minecraft…", 1),
                 ("Preparando Fabric…", 1), ("Preparando Java…", 1),
                 ("Iniciando Minecraft…", 2), ("Iniciando Minecraft para entrar a play.ejemplo.com…", 2),
                 ("Minecraft abierto · Alex", 3), ("", 0))
        for message, step in cases:
            self.assertEqual(lz.stage(message)[0], step, message)

    def test_text_is_never_empty(self):
        for message in ("", None, "algo raro"):
            self.assertTrue(lz.stage(message)[1])

    def test_states(self):
        self.assertEqual([lz.state_of(i, 1) for i in range(4)], ["done", "active", "pending", "pending"])
        self.assertEqual(lz.state_of(3, 3), "done")
        self.assertEqual(lz.state_of(1, 1, failed=True), "failed")
        self.assertEqual(lz.state_of(0, 1, failed=True), "done")


if __name__ == "__main__":
    unittest.main()
