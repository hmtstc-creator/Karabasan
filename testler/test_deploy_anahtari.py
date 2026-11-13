"""araclar/deploy_anahtari.sh: sahte ssh-keygen ve sahte python3 ile prova.

Sınanan: anahtar üretilir, özel kısım 600, mesaja yalnız genel kısım girer,
ikinci çalıştırmada üstüne yazılmaz ve mesaj bir kez gider.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BETIK = os.path.join(KOK, "araclar", "deploy_anahtari.sh")


@unittest.skipUnless(shutil.which("bash"), "bash yok")
class DeployAnahtari(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "bin"))
        self._yaz("bin/ssh-keygen", '#!/bin/bash\nwhile [ $# -gt 0 ]; do [ "$1" = "-f" ] && F="$2"; shift; done\n'
                  'echo OZEL-GIZLI > "$F"; echo "ssh-ed25519 GENEL karabasan-sunucu-deploy" > "$F.pub"\n')
        self._yaz("bin/python3", f'#!/bin/bash\necho "$4" >> {self.d}/mesaj.txt\n')
        self.env = dict(os.environ, PATH=os.path.join(self.d, "bin") + ":/usr/bin:/bin",
                        KARABASAN_SSH_KLASORU=os.path.join(self.d, "ssh"),
                        KARABASAN_DURUM_KLASORU=os.path.join(self.d, "durum"))

    def _yaz(self, ad, icerik):
        yol = os.path.join(self.d, ad)
        with open(yol, "w") as f:
            f.write(icerik)
        os.chmod(yol, 0o755)

    def _calistir(self):
        return subprocess.run(["bash", BETIK], env=self.env, capture_output=True, text=True)

    def test_uretir_bir_kez_bildirir_ozelini_yollamaz(self):
        self.assertEqual(self._calistir().returncode, 0)
        self.assertEqual(self._calistir().returncode, 0)
        ozel = os.path.join(self.d, "ssh", "karabasan_deploy")
        self.assertEqual(oct(os.stat(ozel).st_mode & 0o777), "0o600")
        with open(os.path.join(self.d, "mesaj.txt")) as f:
            mesaj = f.read()
        self.assertEqual(mesaj.count("ssh-ed25519 GENEL"), 1)
        self.assertNotIn("OZEL-GIZLI", mesaj)

    def test_var_olan_anahtarin_ustune_yazmaz(self):
        os.makedirs(os.path.join(self.d, "ssh"))
        ozel = os.path.join(self.d, "ssh", "karabasan_deploy")
        with open(ozel, "w") as f:
            f.write("ESKI")
        with open(ozel + ".pub", "w") as f:
            f.write("ssh-ed25519 ESKI-GENEL x\n")
        self._calistir()
        with open(ozel) as f:
            self.assertEqual(f.read(), "ESKI")


if __name__ == "__main__":
    unittest.main()
