#!/usr/bin/env bash
# Установка всего для clipkit: python-пакеты, голос Silero, шрифты Montserrat, ffmpeg.
# Использование: bash setup.sh [папка_моделей]   (по умолчанию ~/video/models)
set -e
MD="${1:-$HOME/video/models}"
mkdir -p "$MD"
python3 -c "import torch" 2>/dev/null || pip install torch --index-url https://download.pytorch.org/whl/cpu --break-system-packages -q
pip install faster-whisper omegaconf numpy pillow --break-system-packages -q
[ -s "$MD/v4_ru.pt" ] || curl -sSL -o "$MD/v4_ru.pt" https://models.silero.ai/models/tts/ru/v4_ru.pt
for f in Montserrat-Black Montserrat-ExtraBold Montserrat-Bold; do
  [ -s "$MD/$f.ttf" ] || curl -sSL -o "$MD/$f.ttf" "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/$f.ttf"
done
if ! command -v ffmpeg >/dev/null; then
  pip install imageio-ffmpeg --break-system-packages -q
  ln -sf "$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')" /usr/local/bin/ffmpeg
fi
python3 - "$MD" <<'PY'
import sys, torch
from PIL import ImageFont
md = sys.argv[1]
torch.package.PackageImporter(f"{md}/v4_ru.pt").load_pickle("tts_models", "model")
for f in ("Black", "ExtraBold", "Bold"): ImageFont.truetype(f"{md}/Montserrat-{f}.ttf", 40)
print("clipkit setup OK")
PY
