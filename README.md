# novostimania-tools

Инструменты канала «Новостимания».

## clipkit — «Видео дня»

Вертикальное видео 1080×1920 по сценарию: озвучка диктором (Silero, офлайн), моушн-графика, субтитры с подсветкой слов, своя фоновая музыка и звуковые эффекты (без чужих авторских прав).

```bash
bash setup.sh ~/video/models
python3 clipkit.py scenario.json video.mp4 ~/video/models preview   # кадры для проверки в work/pv*.png
python3 clipkit.py scenario.json video.mp4 ~/video/models           # полный рендер
```

Формат сценария — см. `example_scenario.json`. Типы сцен: `hook`, `photo`, `stat`, `compare`, `quote`; концовка с призывом подписаться добавляется автоматически.

В тексте диктора (`say`) числа пишутся как `{цифры|словами}` — в субтитрах будут цифры, диктор прочитает слова. `+` перед гласной ставит ударение.

## Обложка клипа

```bash
python3 clipkit.py scenario.json cover.jpg ~/video/models cover   # cover.jpg 1080×1920 + cover_thumb.jpg (превью для Telegram)
```

Настраивается полем `cover` в сценарии (необязательно — без него всё берётся из хука и сцены сравнения):

- `style`: `compare` (инфографика сравнения, по умолчанию, если есть сцена `compare`) или `title` (крупный заголовок на фото);
- `title` (2 строки, вопрос-цепляшка), `accent` (номер жёлтой строки), `badge`;
- для `compare`: `shape` — `mountain` (высоты гор) или `bar` (всё остальное), `items` (`name`, `value`, `label`, `image` — фото-заливка), `badge_text`, `space: true` + `ground_image` (космос и планета снизу);
- для `title`: `image`, `focus`, `subline`, `number` (цифра-цепляшка), `caption`.

## Готовая озвучка

Поле `voiceover` в сценарии (путь к mp3/wav всей озвучки одним файлом, например из ElevenLabs) — движок не режет её, а подстраивает сцены и субтитры под голос.
