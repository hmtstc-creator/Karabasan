"""Sınav sürerken strateji dosyalarına dokunan değişikliği yakalar (3. kural).

Kullanım: korunan_dosya_denetimi.py <taban> <uc>
Korunan dosyalar değiştiyse, aradaki commit mesajlarından en az birinde
"[hata-duzeltme]" yazmalı; yoksa çıkış kodu 1 olur. Yalnız standart kütüphane.
"""
import subprocess
import sys

KORUNAN = (
    "karabasan/stratejiler/",
    "karabasan/kural.py",
    "karabasan/gostergeler.py",
    "karabasan/botlar.py",
    "user_data/strategies/",
)
ISARET = "[hata-duzeltme]"


def _git(*arg):
    return subprocess.run(("git",) + arg, check=True, capture_output=True, text=True).stdout


def degisenler(taban, uc):
    return [d for d in _git("diff", "--name-only", f"{taban}...{uc}").splitlines() if d]


def korunanlar(dosyalar):
    return [d for d in dosyalar if d.startswith(KORUNAN)]


def ana(taban, uc):
    k = korunanlar(degisenler(taban, uc))
    if not k:
        print("Korunan dosyaya dokunulmamış.")
        return 0
    if ISARET in _git("log", f"{taban}..{uc}", "--format=%B"):
        print("Korunan dosya değişti; hata düzeltmesi olarak işaretli:", *k, sep="\n  ")
        return 0
    print("DURDUR: sınav sürerken korunan dosya değişemez (3. kural). Gerçek bir hata düzeltmesiyse "
          f"commit mesajına {ISARET} yaz.", *k, sep="\n  ")
    return 1


if __name__ == "__main__":
    sys.exit(ana(sys.argv[1], sys.argv[2]))
