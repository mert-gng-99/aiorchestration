# AI Orchestration — Claude Code + Codex

[English README](README.md) · [GitHub](https://github.com/mert-gng-99/aiorchestration)

Verdiğin işi mevcut AI'ları ekip gibi koordine ederek, ilgili diğer
skill'lerle birlikte tamamlatan taşınabilir skill. İlk kullanımda
erişimlerini, erişim türünü ve bütçeyi sorar; yönetici seçimini seninle yapar.

Varsayılan sıra: **Opus 5.5 max → GPT 6.1 Sol medium → Sonnet 5.5 →
Haiku 5.5 → Gemini 3.8 high → doğrulanmış ücretsiz OpenCode modelleri**.
Bu tercih sırasıdır; gerçek model ID'leri ve hesap erişimi kurulumda
kontrol edilir. Profil düzenlenebilir.

## Kurulum

Python 3.10+ gerekir. ZIP'i aç, bu README'nin bulunduğu klasörde çalıştır:

```text
python install.py --target both
```

Yalnız bir ürün için `--target claude` veya `--target codex` kullan.
Kurulum sadece skill dosyalarını kopyalar; CLI/abonelik/anahtar sağlamaz.
Farklı içerikte mevcut skill varsa üzerine yazmaz. İnceledikten sonra
güncellemek için `--replace` kullan; önceki sürüm yedeklenir. Aynı kurulum
tekrarı değişiklik yapmaz.

- Codex: `~/.agents/skills/aiorchestration/`
- Claude Code: `~/.claude/skills/aiorchestration/`

Keşif yolları [Codex](https://learn.chatgpt.com/docs/build-skills) ve
[Claude Code](https://code.claude.com/docs/en/skills) belgelerine dayanır.
Yeni sohbet/oturum aç; Claude Code'da gerekirse `/reload-skills`.

## Kullanım

Claude Code:

```text
/aiorchestration Bu projedeki giriş ekranını yap; ilgili tasarım skill'ini kullan.
```

Codex:

```text
$aiorchestration Bu projedeki giriş ekranını yap; ilgili tasarım skill'ini kullan.
```

Çağrı biçimleri [Codex](https://learn.chatgpt.com/docs/build-skills) ve
[Claude Code](https://code.claude.com/docs/en/skills) belgelerinde açıklanır.
Web/app içinde düz `/aiorchestration` mesajı her üründe özel komut kaydı
oluşturmaz. Paket yerel skill keşfi olan Codex ve Claude Code içindir;
claude.ai/Cowork hesabına yükleme yapılmış değildir.

İlk soruyu cevapla: sağlayıcılar, abonelik CLI/API/web erişimi ve izinli
bütçe. Skill bağlantıları kontrol eder, yönetici adayını sorar ve
kişisel profili oluşturur. API gerekiyorsa anahtarı **kendi terminalinde
veya secret ayarında** tanımlarsın; sohbete/ZIP'e koymazsın.
Profil: `~/.aiorchestration/profile.json`.

## Gerçekte ne yapıyor?

SKILL.md koordinasyonu tanımlar. `scripts/orchestrate.py` erişim kontrolü,
model listesi, yönetici adayları ve gerçek API/CLI metin çağrılarını sağlar.
Yönetici başka AI ise plan ve denetim ona gönderilir; açık sohbet yerel
araçları çalıştırır. Skill açık sohbet modelini otomatik değiştirmez.
Kod/taslak yerel koordinatörce uygulanır ve doğrulanır. Worker'ın bütün
skill'lere kendiliğinden eriştiği varsayılmaz.

Köprüler: Claude Code, Codex, OpenCode CLI; Anthropic Messages, OpenAI
Responses, Gemini generateContent API. Gemini CLI/native/manuel erişimi
host yönetebilir; paket Gemini CLI adaptörü içermez. Web-only erişimde
manuel aktarım veya kullanıcının seçtiği tek-model çalışma kullanılır.

Ek Python paketi gerekmez. `doctor` anahtar/auth içeriği göstermez.
`call` ücretli/belirsiz kayıtta `--allow-paid` ister; skill bu bayrağı
yalnız sen izin verdiysen ekler. API çıktı token sınırı/zaman aşımı vardır;
kesin dolar sınırı ve toplam çağrı hesabı için koordinatör takibi ve
sağlayıcı spend limitleri gerekir.

```text
python aiorchestration/scripts/orchestrate.py doctor
python aiorchestration/scripts/orchestrate.py init
python aiorchestration/scripts/orchestrate.py plan
python -m unittest discover -s tests -v
```

[Erişim rehberi](aiorchestration/references/access.md) ·
[Görev devri örnekleri](aiorchestration/references/workflow.md).

## Arkadaşlarınla paylaşma

`aiorchestration-package.zip` dosyasını gönder. Arkadaşın ZIP'i açıp
`python install.py --target both` çalıştırır ve ilk kullanımda kendi
erişimlerini tanımlar. Paket kişisel profil, anahtar, auth dosyası veya
görev çıktısı içermez. Diğer skill'lerin kendileri ZIP'te bulunmaz;
orchestration alıcının ortamında bulunan ilgili skill'leri kullanır.

## Doğrulama kapsamı

Offline testler: seçim sırası, ücretli izin/ücretsiz tarih kontrolü,
API payload/yanıt ayrıştırma, başarısız/kesilmiş yanıtlar, secret
redaksiyonu, CLI argümanları ve kurulum/yedekleme. Gerçek model üretimi
hesaba, kotaya ve güncel erişime bağlıdır; hazırlanırken ücretli üretim
çağrısı yapılmadı.
