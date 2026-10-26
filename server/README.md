# vkgate — фото к постам ВК через сервер

Ключ сообщества (`VK_TOKEN`) в ВК умеет только `wall.post` без вложений. Чтобы бот ставил посты с картинкой, на сервере работает шлюз `vkgate.py`: он держит ключ пользователя VK ID (администратор группы), сам продлевает его каждый час, загружает фото и ставит отложенный пост.

Бот (`nm.publish vk --photo post.jpg`) отправляет шлюзу текст, время и картинку. Если шлюз недоступен — пост уходит только текстом через `VK_TOKEN`, а картинка приходит владельцу в Telegram, как раньше.

## Установка (один раз)

1. Приложение на id.vk.com → «Доступы»: включить «Стена», «Фотографии», «Видео», «Сообщества». В доверенных Redirect URL должен быть `https://oauth.vk.com/blank.html`.
2. На сервере от root:
   ```bash
   git clone https://github.com/ipdaegorov-code/novostimania-tools.git /root/novostimania-tools
   bash /root/novostimania-tools/server/install.sh <ID приложения>
   ```
   Скрипт напечатает `NM_GATE_URL` и `NM_GATE_KEY`.
3. Вход: `vkgate login-url` → открыть ссылку в браузере под аккаунтом администратора группы → после входа откроется пустая страница `oauth.vk.com/blank.html?code=…` → скопировать адрес целиком → `vkgate login '<адрес>'` (код живёт 10 минут).
4. Проверка: `vkgate check` → `"ok": true, "admin": true, "photo_upload": true`.
5. В окружение задачи бота добавить `NM_GATE_URL` и `NM_GATE_KEY`; если сеть окружения ограничена — домен `…sslip.io` в разрешённые.

## Обслуживание

- Логи: `journalctl -u nmgate -n 50`; состояние: `curl -s https://<адрес>/health`.
- Обновить код: `git -C /root/novostimania-tools pull && bash /root/novostimania-tools/server/install.sh <ID>`.
- Ключ перестал продлеваться (сменили пароль, завершили сеансы) — `vkgate login-url` и `vkgate login` заново.
