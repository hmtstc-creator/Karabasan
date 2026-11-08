---
name: yenikonu
description: Ahmet "/yenikonu" yazınca çalışır. Bitirilen işi wiki arşivine yazıp yeni, temiz bir sohbete geçmeyi hazırlar; yeni sohbette ise yalnız ilgili wiki sayfalarını okuyarak o konuya başlar.
---

# /yenikonu

Amaç: her iş için temiz bir sohbet açmak, geçmişi her seferinde baştan okumamak (token tasarrufu). Ahmet yalnız telefon kullanır;
ondan terminal ya da bilgisayar isteme.

## 1. Kapanış modu (sohbet uzun, Ahmet yeni konuya geçmek istiyor)

`/yenikonu` konu yazmadan ya da "bitti, yeni konu" anlamında geldiyse:

1. Bu sohbette yapılan işi `docs/wiki/` içindeki ilgili sayfaya yaz (yoksa yeni sayfa aç ve `docs/wiki/README.md` tablosuna ekle).
   Karar, neden, sınanan / sınanmayan, "gerçek sunucuda ilk kez" notları. Kaynak olarak yalnız bu sohbette gerçekten olanı yaz.
2. `docs/wiki/gunluk.md` tablosuna bir satır ekle; "Açık işler" bölümünü güncelle.
3. Testleri çalıştır (`python3 -m unittest discover -s testler -t .`). Geçmiyorsa `main`'e işleme, önce düzelt.
4. `main`'e işle ve it (Ahmet'in kuralı: onay beklenmez).
5. Ahmet'e iki üç cümleyle söyle: neyin arşive yazıldığı ve **"Yeni sohbet aç ve ilk mesaja `/yenikonu <konu>` yaz"**. Konu önerisi ver.

## 2. Açılış modu (`/yenikonu <konu>`, yeni sohbetin ilk mesajı)

1. `CLAUDE.md` zaten yüklenir (kısa). Başka büyük dosya okuma.
2. `docs/wiki/README.md`'yi oku, konuyla ilgili en çok 2–3 sayfayı seç, yalnız onları oku (`gunluk.md`'nin sonundaki "Açık işler" dahil).
3. Ahmet'e 3–4 cümleyle özetle: konu hakkında arşivde ne var, ne eksik, ilk adımın ne olacak. Sonra işe başla.
4. İş bitince 1. moddaki yazma adımlarını yap.

## Kurallar

- Wiki'ye gizli bilgi (parola, anahtar, sunucu adresi) yazma.
- Arşivi değiştirirken eski kayıtları silme; yeni bilgi eskisini çürütüyorsa eskinin altına tarihli düzeltme ekle.
- Özet uydurma: arşivde olmayan şeyi "biliyorum" gibi anlatma; sunucudan bilgi gerekiyorsa sunucu oturumuna sor (CLAUDE.md, "Sunucudan bilgi almak").
