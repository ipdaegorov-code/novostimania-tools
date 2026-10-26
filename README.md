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

Для бота: `python3 -m nm.voice make --scenario scenario.json` озвучивает весь сценарий через ElevenLabs (ключ `ELEVENLABS_API_KEY`, голос `ELEVENLABS_VOICE_ID` или `video_of_day.eleven_voice_id` в `config.json`) и сам ставит `voiceover`. `python3 -m nm.voice voices` — список голосов аккаунта.

## Живое видео и графика поверх

У любой сцены вместо (или вместе с) `image` можно указать `video` — путь к mp4. Ролик обрезается под 9:16, идёт по кругу, лёгкий наезд.

- `video_start` — с какой секунды ролика начинать;
- `focus: [x, y]` — какую часть кадра оставить при обрезке;
- у `stat` и `compare`: `blur` (0 — чёткое видео под цифрой) и `dim` (затемнение 0–1);
- `callout` у `photo`/`stat`/`compare`: `{"x":0.63,"y":0.6,"text":"Каньон","at_word":1,"r":120,"pos":"up"}` — жёлтое кольцо с пульсом и плашкой на объекте (x, y — доли кадра 9:16).

Концовка берёт фон (фото или видео) из первой сцены.

## Бот постов (модули `nm/`)

Бот работает как две задачи по расписанию: каждая клонирует репозиторий и выполняет инструкцию из `prompts/`:

- `prompts/post.md` — пост по слоту (слоты, рубрики, хэштеги — в `config.json`);
- `prompts/video.md` — «Видео дня» (21:40).

Модули печатают JSON, ключи берут из окружения (`VK_TOKEN`, `TG_TOKEN`, `MAX_TOKEN`, `PIXABAY_KEY`, для озвучки — `ELEVENLABS_API_KEY`, для фото в ВК — `NM_GATE_URL`, `NM_GATE_KEY`) и никогда их не выводят:

| модуль | что делает |
|---|---|
| `nm.slot` | текущий слот, время публикации, срок диалога |
| `nm.card` | айдентика, квадрат, затемнение, бейджи, флаги, синий фон |
| `nm.photos` | поиск свободных фото и видео (Pixabay, Openverse, Wikimedia, NASA), портреты, скачивание с проверкой |
| `nm.approve` | превью владельцу и ожидание ответов в Telegram |
| `nm.voice` | озвучка «Видео дня» через ElevenLabs |
| `nm.publish` | ВК (отложенный пост, с картинкой — через шлюз `server/vkgate.py`, см. `server/README.md`), Telegram, MAX, последние посты MAX |

Справка по командам — в начале каждого файла.
