"""Sunucu oturumunun `sunucu/...` dallarını sınar, geçerse ana dala birleştirir.

GitHub Actions içinden `main`'in kendi kopyasıyla çalışır (docs/wiki/sunucu-github-yetkisi.md).
Dalın kendi iş akışı çalıştırılmaz; böylece dal denetimi gevşetemez.

Kurallar:
- Korunan yollara (denetim araçları, iş akışları, CLAUDE.md) dokunan dal birleştirilmez; PR açık kalır, elle incelenir.
- Birleştirmeden önce testler dalın kodunda çalışır; denetim dosyaları main'deki sürümle değiştirilir.
- Strateji dosyalarına dokunan dal yalnız commit mesajında [hata-duzeltme] varsa geçer (korunan_dosya_denetimi.py).
"""
import json
import os
import subprocess
import sys
import tempfile

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPO = os.environ.get("GITHUB_REPOSITORY", "hmtstc-creator/Karabasan")
KORUNAN_YOLLAR = (
    ".github/",
    "araclar/korunan_dosya_denetimi.py",
    "araclar/sunucu_dal_birlestir.py",
    "testler/test_guvenlik_kapisi.py",
    "testler/test_sunucu_dal_birlestir.py",
    "CLAUDE.md",
)
DENETIM_DOSYALARI = (
    "araclar/korunan_dosya_denetimi.py",
    "testler/test_guvenlik_kapisi.py",
)


def korunana_dokunan(dosyalar):
    return [d for d in dosyalar if d.startswith(KORUNAN_YOLLAR)]


def calistir(*arg, cwd=None, kontrol=True):
    return subprocess.run(arg, cwd=cwd or KOK, check=kontrol, capture_output=True, text=True)


def api(yontem, yol, **alan):
    arg = ["gh", "api", "-X", yontem, f"repos/{DEPO}/{yol}"]
    for k, v in alan.items():
        arg += ["-f", f"{k}={v}"]
    s = calistir(*arg, kontrol=False)
    return s.returncode, s.stdout, s.stderr


def dallar():
    s = calistir("git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/sunucu/")
    return [d.strip() for d in s.stdout.splitlines() if d.strip()]


def pr_bul_ya_da_ac(dal):
    ad = dal.replace("origin/", "", 1)
    kod, cikti, _ = api("GET", f"pulls?head={DEPO.split('/')[0]}:{ad}&state=open")
    if kod == 0 and json.loads(cikti or "[]"):
        return json.loads(cikti)[0]["number"]
    kod, cikti, hata = api("POST", "pulls", title=f"Sunucu: {ad}", head=ad, base="main",
                           body="Sunucu oturumunun düzeltmesi. Testler geçerse kendiliğinden birleştirilir.")
    if kod != 0:
        print("PR açılamadı:", hata)
        return None
    return json.loads(cikti)["number"]


def dal_isle(dal):
    ad = dal.replace("origin/", "", 1)
    dosyalar = calistir("git", "diff", "--name-only", f"origin/main...{dal}").stdout.split()
    if not dosyalar:
        print(f"{ad}: main'den farkı yok, atlandı.")
        return
    pr = pr_bul_ya_da_ac(dal)
    if pr is None:
        return
    k = korunana_dokunan(dosyalar)
    if k:
        print(f"{ad}: korunan yola dokunuyor, elle incelenecek (PR #{pr}):", *k)
        return
    if calistir(sys.executable, "araclar/korunan_dosya_denetimi.py", "origin/main", dal, kontrol=False).returncode != 0:
        print(f"{ad}: korunan dosya denetimi başarısız (PR #{pr}).")
        return
    with tempfile.TemporaryDirectory() as gecici:
        calc = os.path.join(gecici, "dal")
        calistir("git", "worktree", "add", "--detach", calc, dal)
        try:
            birles = calistir("git", "merge", "--no-edit", "origin/main", cwd=calc, kontrol=False)
            if birles.returncode != 0:
                print(f"{ad}: main ile çakışıyor, atlandı (PR #{pr}).")
                return
            for d in DENETIM_DOSYALARI:  # dal denetimi gevşetemesin
                with open(os.path.join(KOK, d), "rb") as f, open(os.path.join(calc, d), "wb") as g:
                    g.write(f.read())
            t = calistir(sys.executable, "-m", "unittest", "discover", "-s", "testler", "-t", ".", cwd=calc, kontrol=False)
            if t.returncode != 0:
                print(f"{ad}: testler geçmedi (PR #{pr}).\n", t.stderr[-1500:])
                return
        finally:
            calistir("git", "worktree", "remove", "--force", calc, kontrol=False)
    kod, _, hata = api("PUT", f"pulls/{pr}/merge", merge_method="squash")
    if kod != 0:
        print(f"{ad}: birleştirilemedi (PR #{pr}):", hata)
        return
    api("DELETE", f"git/refs/heads/{ad}")
    print(f"{ad}: testler geçti, PR #{pr} birleştirildi.")


def ana():
    calistir("git", "fetch", "-q", "origin", "main", "+refs/heads/sunucu/*:refs/remotes/origin/sunucu/*")
    for dal in dallar():
        dal_isle(dal)
    return 0


if __name__ == "__main__":
    sys.exit(ana())
