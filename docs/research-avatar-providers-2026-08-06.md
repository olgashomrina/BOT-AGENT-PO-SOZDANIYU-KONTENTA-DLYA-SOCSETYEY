# Рынок говорящих видео-аватаров и липсинка — разведка цен

Дата: 2026-08-06. Курс для пересчёта: **101 ₽ за $1**.

Задача: вертикальные ролики 30–90 секунд из одной фотографии + озвучки, регулярный
выпуск в Telegram и YouTube. Опорная точка — замер заказчика на агрегаторе Runware:
модель `heygen:avatar@4` (HeyGen Avatar IV) стоила **$0.489 за 5 секунд**, то есть
$0.0978/с ≈ **$5.87 за минуту ≈ 593 ₽**. Ищем то же качество рта дешевле.

Все цифры ниже взяты только с официальных страниц вендоров и агрегаторов. То, что
подтвердить не удалось, вынесено в отдельный раздел в конце — там нет догадок.

---

## Краткий вывод

**Главная находка: тот же движок HeyGen Avatar IV в собственном API HeyGen стоит
$0.05 за секунду — это $3.00 за минуту (303 ₽), почти вдвое дешевле Runware.**
Агрегатор накручивал ~2× сверху. Разовая плата за создание фото-аватара — $1.00,
она платится один раз на фотографию, а не на ролик.

Расклад по трём стратегиям:

1. **Нужен ровно рот Avatar IV, из фото, программно** → прямой API HeyGen,
   **$3.00/мин (303 ₽)** + $1.00 за аватар единоразово. Экономия против Runware
   ≈ 49 %. Ролик 60 с = $3.00 ≈ 303 ₽, ролик 30 с = $1.50 ≈ 152 ₽.

2. **Нужен рот Avatar IV, но API не обязателен** → подписка HeyGen Creator
   $29/мес даёт 600 кредитов, Avatar IV расходует 20 кредитов/мин → 30 минут
   в месяц, то есть **≈ $0.97/мин (98 ₽)**. При годовой оплате $24/мес → **$0.80/мин
   (81 ₽)**. Это самый дешёвый способ получить именно это качество, но на странице
   тарифов доступ к API у Creator и Pro не указан — это ручной веб-интерфейс.
   При регулярном выпуске 30 роликов по 60 с в месяц лимит выбирается ровно.

3. **Готовы на другой движок ради цены** → две реальные альтернативы:
   - **Hedra Character-3**, подписка Professional $75/мес: 14 400 кредитов при
     расходе 6 кредитов/секунду = 40 минут → **$1.88/мин (189 ₽)**. Заявлена полная
     мультиязычность, длина до 10 минут, вертикаль 9:16 — по формату подходит лучше всех.
   - **Pruna P Video Avatar** на Segmind: **$0.03125/с в 720p = $1.88/мин (189 ₽)**,
     $0.05625/с в 1080p = $3.38/мин (341 ₽). Самый дешёвый из «фото + звук → видео»
     с публично опубликованной ценой.

**Чего делать не надо:** OmniHuman на fal.ai ($0.14/с = $8.40/мин, 848 ₽, к тому же
жёсткий лимит 30 секунд аудио), InfiniteTalk на fal.ai ($0.20/с, в 720p $0.40/с =
$24/мин, 2424 ₽) и HeyGen Avatar IV на Segmind ($0.125/с = $7.50/мин, 758 ₽ —
дороже даже Runware). Все три дороже исходной точки.

**Отдельно про липсинк по видео-донору.** Если сценарий допускает не «фото →
видео», а «готовый кусок видео + новое аудио», цены падают на порядок:
Kling lipsync на fal.ai — **$0.014 за секунду входного видео = $0.84/мин (85 ₽)**,
LatentSync на fal.ai — **$0.005/с = $0.30/мин (30 ₽)**. Это другой продукт (нужен
донор-ролик, а не фотография), но для регулярного выпуска разница решающая.

---

## Сводная таблица

Цена за минуту готового ролика. Пересчёт в рубли по 101 ₽/$. «Мин» — минимальный
практический счёт за минуту при указанном тарифе.

### Прямые провайдеры

| Провайдер / продукт | $/мин | ₽/мин | API | Русский | Длина ролика |
|---|---|---|---|---|---|
| **HeyGen Avatar IV, Photo Avatar, API** | **$3.00** | **303 ₽** | да, pay-as-you-go | не подтверждён | до 30 мин на выходе, аудио до 10 мин |
| HeyGen Avatar IV, Digital Twin / Studio, API | $4.00 | 404 ₽ | да | не подтверждён | то же |
| HeyGen Avatar V, API | $4.00 | 404 ₽ | да | не подтверждён | то же |
| HeyGen Avatar III, Digital Twin / Studio, API | $1.00 | 101 ₽ | да | не подтверждён | то же |
| HeyGen Avatar III, Photo Avatar, API | $2.60 | 263 ₽ | да | не подтверждён | то же |
| **HeyGen Creator, подписка $29/мес** | **$0.97** | **98 ₽** | нет (не указан) | не подтверждён | до 30 мин на ролик |
| HeyGen Creator, годовая $24/мес | $0.80 | 81 ₽ | нет (не указан) | не подтверждён | до 30 мин на ролик |
| HeyGen Pro, подписка $49/мес | $0.98 | 99 ₽ | нет (не указан) | не подтверждён | до 30 мин на ролик |
| **Hedra Character-3, Professional $75/мес** | **$1.88** | **189 ₽** | да, отдельный USD-кошелёк | «full multi-language support» | до 10 мин |
| Hedra Character-3, Creator $30/мес | $2.00 | 202 ₽ | да | то же | до 10 мин |
| Hedra Character-3, Basic $15/мес | $3.60 | 364 ₽ | да | то же | до 10 мин |
| Synthesia Creator $89/мес | $2.97 | 300 ₽ | да, 360 мин/год включено | 160+ языков (список не открыт) | не указана |
| Synthesia Creator, годовая $64/мес | $2.13 | 215 ₽ | да | то же | не указана |
| Vozo Studio $99/мес | $1.65 | 167 ₽ | только Enterprise | не подтверждён | не указана |
| Vozo Creator $29/мес | $1.93 | 195 ₽ | только Enterprise | не подтверждён | не указана |
| Argil | не подтверждена | — | да, кредитная | не подтверждён | не подтверждена |
| Akool | не подтверждена | — | да, от Pro Max | не подтверждён | 15/30/45/60 мин по тарифам |
| D-ID | не подтверждена | — | да, отдельные API-планы | не подтверждён | кратно 15 с |
| Captions / Mirage | не подтверждена | — | не подтверждён | не подтверждён | не подтверждена |
| Creatify | не подтверждена | — | только Enterprise | не подтверждён | не подтверждена |
| Vidnoz | не подтверждена | — | не подтверждён | не подтверждён | до 60 мин на платных |
| Kling официальный API | не подтверждена | — | да | не подтверждён | не подтверждена |
| Higgsfield | не подтверждена | — | есть Cloud API | не подтверждён | не подтверждена |

### Агрегаторы — модели «фото/картинка + звук → говорящее видео»

| Модель у агрегатора | Цена | $/мин | ₽/мин | Лимит длины |
|---|---|---|---|---|
| **Pruna P Video Avatar, Segmind, 720p** | $0.03125/с | **$1.88** | **189 ₽** | не указан |
| Pruna P Video Avatar, Segmind, 1080p | $0.05625/с | $3.38 | 341 ₽ | не указан |
| Creatify Aurora, fal.ai, 480p | $0.07/с | $4.20 | 424 ₽ | не указан |
| Creatify Aurora, fal.ai, 720p | $0.14/с | $8.40 | 848 ₽ | не указан |
| Kling Avatar V2 Standard, Segmind | $0.071/с | $4.26 | 430 ₽ | не указан |
| VEED Fabric 1.0, fal.ai, 480p | $0.08/с | $4.80 | 485 ₽ | не указан |
| VEED Fabric 1.0, fal.ai, 720p | $0.15/с | $9.00 | 909 ₽ | не указан |
| HeyGen Avatar IV, Runware (замер заказчика) | $0.489/5 с | $5.87 | 593 ₽ | — |
| HeyGen Avatar IV, Segmind | $0.125/с | $7.50 | 758 ₽ | не указан |
| OmniHuman v1, fal.ai | $0.14/с | $8.40 | 848 ₽ | **аудио ≤ 30 с** |
| OmniHuman v1.5, fal.ai | $0.16/с | $9.60 | 970 ₽ | не указан |
| MultiTalk («AI Avatar»), fal.ai | $0.20/с, 720p ×2 | $12.00 / $24.00 | 1212 / 2424 ₽ | не указан |
| InfiniteTalk, fal.ai | $0.20/с, 720p ×2 | $12.00 / $24.00 | 1212 / 2424 ₽ | не указан |

### Агрегаторы — липсинк по видео-донору

| Модель у агрегатора | Цена | $/мин | ₽/мин | Лимит длины |
|---|---|---|---|---|
| **LatentSync, fal.ai** | $0.005/с, минимум $0.20 | **$0.30** | **30 ₽** | — |
| **Kling lipsync, fal.ai** | $0.014/с входного видео, округление до 5 с | **$0.84** | **85 ₽** | видео 2–10 с, аудио 2–60 с |
| LatentSync, Replicate | ≈ $0.099 за прогон | зависит от длины | — | не указан |
| PixVerse Lipsync, Segmind | $0.03/с | $1.80 | 182 ₽ | не указан |
| HeyGen Lipsync Speed, Replicate | $0.0333/с | $2.00 | 202 ₽ | не указан |
| Sync Lipsync 2.0, fal.ai | $3/мин | $3.00 | 303 ₽ | не указан |
| HeyGen Lipsync Precision, Replicate | $0.0667/с | $4.00 | 404 ₽ | не указан |
| Sync.so Lipsync 2 Pro, Segmind | $0.084/с | $5.04 | 509 ₽ | не указан |
| Sync Lipsync 2.0 Pro, fal.ai | $5/мин | $5.00 | 505 ₽ | не указан |
| VEED Lipsync v2, Segmind | $4.2/мин | $4.20 | 424 ₽ | не указан |
| Wan-2.2 Animate Move, fal.ai | $0.08/«видео-секунду» 720p, где секунда = 16 кадров | зависит от fps | — | не указан |

---

## Разбор по провайдерам

### HeyGen

**API, pay-as-you-go.** Прайс опубликован в документации для разработчиков.
Модель — предоплаченный кошелёк в долларах, «no monthly subscription, no commitments»,
баланс читается через `/v3/users/me`.

Дословно со страницы:

| Продукт | Цена |
|---|---|
| Avatar V (Digital Twin) | $0.0667 / sec |
| **Avatar IV, Photo Avatar** | **$0.05 / sec** |
| Avatar IV, Digital Twin | $0.0667 / sec |
| Avatar IV, Studio Avatar | $0.0667 / sec |
| Avatar III, Digital Twin | $0.0167 / sec |
| Avatar III, Studio Avatar | $0.0167 / sec |
| Avatar III, Photo Avatar | $0.0433 / sec |
| Cinematic Avatar | $7.00 / video |
| Video Agent (Prompt to Video) | $0.0333 / sec |
| Lipsync, Speed | $0.0333 / sec |
| Lipsync, Precision | $0.0667 / sec |
| Video Translation | $0.0333 – $0.0667 / sec |
| HyperFrames | $0.10 / min (1080p30) – $0.30 / min (4K60) |
| AI Clipping | $0.15 / clip |
| Filler Word Removal | $0.01 / sec исходника, минимум 1 минута |
| Text-to-Speech (Starfish) | $0.000667 / sec |
| **Avatar Creation, Photo Avatar** | **$1.00 per call** |
| Avatar Creation, Digital Twin | $1.00 per call |

Источник: <https://developers.heygen.com/docs/pricing.md>

**Отдельная плата за создание аватара из фото есть и она разовая — $1.00 за вызов.**
Дальше фото-аватар переиспользуется в любом числе роликов.

**Лимиты** (источник <https://developers.heygen.com/docs/usage-limits.md>):
- «Maximum duration: 30 minutes» на выходное видео;
- аудио на входе — максимум 10 минут (600 секунд);
- скрипт — максимум 5 000 символов;
- 25 fps у аватарных видео, соотношения сторон 16:9 или 9:16 (вертикаль есть);
- разрешение 128–4096 px по стороне, по умолчанию 1080p;
- до 50 сцен в ролике;
- 10 одновременных задач на тарифе Pay-As-You-Go.

**Файл забирается программно.** В ответе на опрос статуса приходит прямая ссылка:
`"status": "completed", "video_url": "https://files.heygen.ai/video/vid_xyz789.mp4"`.
Флоу фото-аватара — `POST /v3/avatars` (загрузка фото), затем `POST /v3/videos`,
затем опрос до `completed`.
Источники: <https://developers.heygen.com/docs/quick-start.md>,
<https://developers.heygen.com/photo-avatar.md>

**Подписки** (источник <https://www.heygen.com/pricing>):

| Тариф | Цена | Кредиты/мес | Макс. длина ролика | API |
|---|---|---|---|---|
| Free | $0 | нет | 1 мин, 3 ролика/мес | нет |
| Creator | $29/мес, $24/мес при годовой | 600 | 30 мин | не указан |
| Pro | $49/мес | 1 000 | 30 мин | не указан |
| Business | $149/мес + $20/место | 1 500 | 60 мин | не указан |
| Enterprise | по запросу | гибко | «No video duration max» | не указан |

Расход кредитов там же: Avatar III — 3 кредита/мин, **Avatar IV/V — 20 кредитов/мин**,
Video Translation (липсинк) — 5 кредитов/мин, Video Agent — 20 кредитов/мин.

Отсюда пересчёт: Creator = 600 / 20 = **30 минут Avatar IV в месяц за $29** →
$0.967/мин ≈ 98 ₽. Pro = 1 000 / 20 = 50 минут за $49 → $0.98/мин ≈ 99 ₽.
Business = 1 500 / 20 = 75 минут за $149 → $1.99/мин ≈ 201 ₽.

⚠️ Важная оговорка: страница тарифов не указывает наличие API у Creator и Pro,
а страница разработчика описывает API как отдельный pay-as-you-go-кошелёк. То есть
дешёвые $0.97/мин — это, судя по первоисточникам, ручной веб-интерфейс, а не автоматизация.
Совмещение подписки и API по официальным страницам не подтверждается.

### Hedra (Character-3)

**Подписки** (источник <https://www.hedra.com/pricing>):

| Тариф | Цена | Кредиты/мес | Минут Character-3 | $/мин |
|---|---|---|---|---|
| Basic | $15/мес | 1 500 | 4.17 | $3.60 ≈ 364 ₽ |
| Creator | $30/мес | 5 400 | 15 | $2.00 ≈ 202 ₽ |
| Professional | $75/мес | 14 400 | 40 | $1.88 ≈ 189 ₽ |
| Teams | $75/мес | 14 400 | 40 | $1.88 ≈ 189 ₽ |
| Enterprise | по запросу | по запросу | — | — |

Там же: «Credits are deducted based on the generated video length», для
Hedra Character-3 ставка **6 кредитов за секунду**. 6 × 60 = 360 кредитов на минуту —
отсюда столбцы выше.

**API есть, он отдельный.** Документация описывает предоплаченный кошелёк в долларах
и эндпоинт `GET /balance`; готовые файлы хранятся 48 часов после завершения задачи
(«Generated media is retained for 48 hours after a job completes — download outputs
to your own storage»). Источник: <https://www.hedra.com/docs/pages/developer/v3/quickstart>

**Character-3, характеристики** (источник
<https://www.hedra.com/docs/api-reference/v3/run-a-model/run-hedra-character-3-hedra-character-3.md>):
- описание модели: «Hedra's latest longform avatar model, audio to video will full
  multi-language support. Perfect for talking and singing video with speaker selection
  **up to 10 minutes long**»;
- аудио на входе — до `600000` мс, то есть 10 минут;
- разрешения 540p / 720p / 1080p;
- соотношения сторон 1:1, 4:3, 3:4, 16:9, **9:16**, 9:21, 21:9 — вертикаль есть;
- результат забирается через `GET /v3/jobs/{job_id}`, ссылки в массиве `outputs[]`;
- **цена за секунду в документации не опубликована** — её надо запрашивать через
  `POST /models/hedra-character-3/estimate`. Поэтому цена API у Hedra в таблице
  выше выведена из подписочных кредитов, а не из прайса API.

Русский язык отдельно не перечислен, заявлена только «full multi-language support».

### Synthesia

Источник: <https://www.synthesia.io/pricing>

| Тариф | Цена | Минут видео | Личных аватаров | API |
|---|---|---|---|---|
| Basic (Free) | $0 | 10 мин/мес | 3 | нет |
| Starter | $29/мес, $18/мес годовая | 10 мин/мес (120 мин/год на годовой) | 1 | нет |
| Creator | $89/мес, $64/мес годовая | 30 мин/мес (360 мин/год на годовой) | 5 | «360 minutes of video / year included. (Additional usage available as a paid add-on)» |
| Enterprise | по запросу | безлимит | безлимит | включён |

Пересчёт: Creator помесячно $89 / 30 мин = **$2.97/мин ≈ 300 ₽**; годовой $64 / 30 мин =
**$2.13/мин ≈ 215 ₽**.

Дополнительно: Studio Avatars — платный аддон **$1 000/год**, только для годовых тарифов.
Заявлено «over 160+ languages and accents»
(<https://www.synthesia.io/features/languages>), но полного списка на этой странице нет,
поэтому наличие русского не считаю подтверждённым.

Отдельной платы за создание личного аватара из фото на странице тарифов нет —
личные аватары входят в тариф числом штук.

### Argil

Источник: <https://docs.argil.ai/resources/api-pricings>

- видео — **160 кредитов за минуту**;
- голос — **20 кредитов за минуту**;
- роялти за аватар — **20 кредитов за видео** (только аватары Argil v1);
- b-roll: 10 кредитов за ИИ-картинку, 20 кредитов за сток-видео;
- прайс действует «для тарифа Classic и выше», Enterprise — от 60 000 кредитов/мес по запросу.

Курс «кредит → доллар» на этой странице не опубликован, поэтому цену за минуту
в долларах вывести нельзя. Страница <https://www.argil.ai/pricing> подгружает
тарифы скриптом («Loading plans…») и статически не читается — суммы $39 / $149 / $499,
которые всплывают в поиске, я взял бы только из вторичных источников, поэтому не привожу.

### Akool

Источник: <https://www.akool.com/api-pricing>

- Talking Avatar, 1080p — **5 кредитов за 10 с**;
- Talking Avatar, 4K — **10 кредитов за 10 с**;
- Talking Photo — **10 кредитов за 5 с**;
- LipSync API — **10 кредитов за 10 с**.

Долларовая стоимость кредита не опубликована: на странице тарифов
(<https://www.akool.com/pricing>) все планы отрисованы как «$0/seat/mo» — цифры
подставляются скриптом. Поэтому цену за минуту посчитать нельзя.

Лимиты длины по тарифам оттуда же: Starter 15 мин, Pro 30 мин, Pro Max 45 мин,
Business 60 мин, Enterprise — по договору. Доступ к API — «Access to API» начиная
с Pro Max.

API отдаёт файл программно: `POST /api/open/v3/talkingavatar/create` возвращает
task ID, `GET /api/open/v3/content/video/infobymodelid` отдаёт ссылку при
`video_status = 3`. Важное ограничение: «The resources (image, video, voice)
generated by our API are valid for **7 days**». Лимит символов на запрос: Pro 5 000,
Pro Max 10 000, Business 50 000.
Источник: <https://docs.akool.com/ai-tools-suite/talking-avatar>

### D-ID

Кредитная механика подтверждена официальным FAQ (<https://www.d-id.com/faqs/>):
«Each credit is worth up to 15 seconds of video. When generating longer videos,
credits add up according to the length of the generated video» — длина округляется
вверх до кратности 15 секундам, ролик 40 с стоит 3 кредита. Для стриминга через API
цена кредита вдвое ниже.

Сами суммы тарифов подтвердить не удалось: страницы `/pricing/studio/` и `/pricing/api/`
отдают только навигацию и футер, таблицы подгружаются скриптом; статья справочного
центра про подписки отвечает HTTP 403. Поэтому $/мин у D-ID не заполняю.

### Captions / Mirage

Источник: <https://www.captions.ai/pricing>

| Тариф | Цена | Кредиты/мес |
|---|---|---|
| Max | $24.99/мес | 500 |
| Scale 1x | $69.99/мес | 1 400 |
| Scale 2x | $139.99/мес | 2 800 |
| Scale 4x | $279.99/мес | 5 600 |
| Enterprise | по запросу | по запросу |

Free-тариф без ИИ-кредитов. Неиспользованные кредиты переносятся, потолок баланса —
трёхмесячный объём тарифа. **Сколько секунд видео стоит один кредит — на странице
не написано**, поэтому цену за минуту вывести нельзя. API и его цена на странице
тарифов не упоминаются.

### Vozo

Источники: <https://www.vozo.ai/pricing>, <https://www.vozo.ai/docs/common/tools-points-rules>

| Тариф | Цена | AI points/мес | Минут липсинка (по странице) | $/мин |
|---|---|---|---|---|
| Free | $0 | 20 | — | — |
| Creator | $29/мес | 150 | ≈ 15 | $1.93 ≈ 195 ₽ |
| Studio | $99/мес | 600 | ≈ 60 | $1.65 ≈ 167 ₽ |
| Studio XL | не отображается | 1 500 | — | — |
| Studio XXL | не отображается | 4 000 | — | — |

Расход по правилам поинтов: Lip Sync — «5 points base + 5 points per minute»
(варианты того же проекта — только 5 поинтов за минуту); Talking Photo — так же;
дубляж — 3 поинта за минуту.

⚠️ Правила поинтов (5/мин) и заявленные «≈15 минут за 150 поинтов» (то есть 10/мин)
между собой не сходятся; беру более консервативную цифру со страницы тарифов.

**API только на Enterprise** — на странице тарифов «API Access» указан исключительно
в Enterprise. Для регулярной автоматизации это отсекающий фактор.

### Creatify

Источник: <https://www.creatify.ai/pricing>

- Starter — $39/мес, 100 кредитов/мес;
- Pro — $99/мес, 300–5 000 кредитов/мес;
- Enterprise — по запросу.

Сколько секунд видео стоит кредит, на странице не сказано → цену за минуту
не вывести. **API заявлен только для Enterprise** («API volume discounts»).

Модель Creatify Aurora при этом доступна на fal.ai по прозрачной цене — см. раздел
агрегаторов.

### Vidnoz

Источник: <https://www.vidnoz.com/pricing.html>

Правила расхода кредитов опубликованы: генерация видео — **0.5 кредита за секунду**
(минимум 1 кредит), «expressive avatars» — **2 кредита за секунду**, ИИ-картинка —
2 кредита. Максимальная длина ролика: 3 минуты на Free, 60 минут на Starter и Business.
Аддоны: Avatar Pro $299/год, Voice Clone $9.99/мес.

⚠️ Помесячные суммы Starter и Business на странице не отображаются (только баннер
«25% OFF First Month»), а объёмы «15 кредитов/мес» и «30 кредитов/мес» при ставке
0.5 кредита/секунду дали бы 30 и 60 секунд видео в месяц — это явно несостыковка
единиц на самой странице. Цену за минуту не вывожу.

### Kling — официальный API

Подтвердить не удалось: `klingai.com/global/dev/pricing` и страница тарификации
ресурсных пакетов в `app.klingai.com` отвечают **HTTP 446** (запрос блокируется).
Официальных цифр нет.

Косвенно: Kling-липсинк и Kling-аватары доступны через агрегаторы с опубликованными
ценами — см. таблицу агрегаторов (fal.ai $0.014/с, Segmind $0.071/с, Runware
$0.0462 за 1–5 с).

### Higgsfield

Подтвердить не удалось: `higgsfield.ai/pricing` отдаёт только шапку, тарифы
подгружаются скриптом; `cloud.higgsfield.ai` отвечает страницей-редиректом;
`higgsfield.ai/api` — 404. Ни цен, ни ставки кредитов из первоисточника получить
не вышло.

---

## Агрегаторы

### Runware (текущий)

Публичный прайс по моделям на сайте не выложен: страница тарифов говорит, что
«pricing varies across thousands of parameters» и отправляет смотреть цену в Playground.
Поэтому единственные достоверные цифры — **собственные замеры заказчика**,
зафиксированные в `kruzhochki.md` этого же репозитория:

| Модель Runware | Цена | За 30 с |
|---|---|---|
| `heygen:avatar@4` (Avatar IV) | $0.489 за 5 с = $0.0978/с | $2.93 ≈ 296 ₽ |
| `klingai:7@1` | $0.0462 за 1–5 с, $0.0924 за 6–10 с, далее $0.0092/с | $0.276 ≈ 28 ₽ |
| `pixverse:lipsync@1` | $0.0136/с аудио | $0.408 ≈ 41 ₽ |
| `sync:lipsync-2@1` | $0.044/с аудио | $1.32 ≈ 133 ₽ |
| `sync:3@0` | $0.133/с | $3.99 ≈ 403 ₽ |

Это не публичный первоисточник, а замер по счёту — помечаю явно.

### fal.ai

Цена печатается прямо на странице модели строкой «Your request will cost …».

| Модель | Страница | Цена дословно |
|---|---|---|
| OmniHuman (ByteDance) | <https://fal.ai/models/fal-ai/bytedance/omnihuman> | «$0.14 per second»; **«Max Audio Duration: 30 seconds»** — жёсткий лимит на уровне API |
| OmniHuman v1.5 | <https://fal.ai/models/fal-ai/bytedance/omnihuman/v1.5> | «Your request will cost $0.16 per second» |
| InfiniteTalk | <https://fal.ai/models/fal-ai/infinitalk> | «Your request will cost $0.2 per second.» + «For 720p price will be doubled» |
| InfiniteTalk (single-text) | <https://fal.ai/models/fal-ai/infinitalk/single-text> | то же: $0.2/с, 720p — вдвое |
| MultiTalk («AI Avatar») | <https://fal.ai/models/fal-ai/ai-avatar> и `/single-text` | «Your request will cost $0.2 per second.» + 720p вдвое. Страница прямо называет движок: «MultiTalk model» |
| Kling lipsync (audio-to-video) | <https://fal.ai/models/fal-ai/kling-video/lipsync/audio-to-video> | «Your request will be priced **$0.014** per input **video seconds**, rolling up to closest **5 second increment**». Лимиты: исходное видео **2–10 с** (≤100 МБ), аудио **2–60 с** (≤5 МБ) |
| Sync Lipsync 2.0 | <https://fal.ai/models/fal-ai/sync-lipsync/v2> | «Your request will cost **$3** per minute of video»; Pro-вариант — $5/мин |
| LatentSync | <https://fal.ai/models/fal-ai/latentsync> | $0.20 за ролик до 40 с, дальше $0.005 за секунду выходного видео (это ровно $0.005/с и минимальный чек $0.20) |
| VEED Fabric 1.0 | <https://fal.ai/models/veed/fabric-1.0> | «480p - $0.08 per second, 720p - $0.15 per second» |
| Creatify Aurora | <https://fal.ai/models/fal-ai/creatify/aurora> | «$0.07 per video second for 480p, $0.14 per video second for 720p generation». Округление вверх: «a generation with an output video of 9.4 seconds will be billed as a 10 second video» |
| Wan-2.2 Animate Move | <https://fal.ai/models/fal-ai/wan/v2.2-14b/animate/move> | «720p: $0.08 per video second, 580p: $0.06, 480p: $0.04». Считается по кадрам: «Request is billed based on the number of frames, at a rate of **16 frames per "video second"**». Пример со страницы: 5 с при 60 fps в 720p = 300 кадров = 18.75 «видео-секунд» = **$1.50** |

⚠️ Про Wan-2.2 Animate: биллинговая «секунда» = 16 кадров, а не реальная секунда.
При 25 fps реальная секунда = 1.5625 биллинговых → $0.125/с в 720p ≈ $7.50/мин.
Дешёвая на вид ставка обманчива.

Не найдены на fal.ai по прямым слугам (404): `fal-ai/sonic`, `fal-ai/wan-s2v`,
`sync/sync-3`, `fal-ai/hedra/character-3`. MuseTalk на fal.ai есть
(<https://fal.ai/models/fal-ai/musetalk>), но плейсхолдер цены на странице показывает
«$0 per compute second» — реальной ставки там нет.

### Segmind

Цена публикуется на подстранице `/pricing` каждой модели.

| Модель | Страница | Цена дословно |
|---|---|---|
| **Pruna P Video Avatar** | <https://www.segmind.com/models/p-video-avatar/pricing> | 720p — **$0.03125** за секунду, 1080p — **$0.05625** за секунду |
| PixVerse Lipsync | <https://www.segmind.com/models/pixverse-lipsync/pricing> | «$0.03 per second (per second of output duration)» |
| Kling Avatar V2 Standard | <https://www.segmind.com/models/kling-v2-standard-avatar/pricing> | «$0.071 /per second (per second of output duration)» |
| Sync.so Lipsync 2 Pro | <https://www.segmind.com/models/sync.so-lipsync-2-pro/pricing> | «$0.084 per video second» (за секунду входного видео) |
| VEED Lipsync v2 | <https://www.segmind.com/models/veed-2-lipsync/pricing> | «$4.2» за минуту выходного видео |
| **HeyGen Avatar IV** | <https://www.segmind.com/models/heygen-avatar-iv/pricing> | **$0.125 за секунду** выходного видео — дороже Runware |
| InfiniteTalk | <https://www.segmind.com/models/infinite-talk/pricing> | «$0.0043 /per gpu second» (serverless); dedicated — $0.0007–$0.0031 за GPU-секунду |

⚠️ InfiniteTalk на Segmind тарифицируется **за секунду работы GPU**, а не за секунду
видео. Со страницы модели известно, что пример генерации занял ~282 с. Итоговая цена
за минуту ролика отсюда не выводится — нужен замер.

Общая тарификация Segmind: универсальные кредиты, pay-as-you-go; подписки
Pro $39/мес (кредитов на $50), Business $99/мес (на $99), Scale $599/мес (на $599),
Flexible от $10. Источник: <https://www.segmind.com/pricing>

Каталог липсинк- и аватар-моделей: <https://www.segmind.com/models/all/lipsync-avatar-models> —
там же есть Kling V1/V2 Pro Avatar, HeyGen Avatar V, VEED Avatars, HappyHorse 1.0/1.1.

### Replicate

Каталог липсинка: <https://replicate.com/collections/lipsync> — sync/lipsync-2 и
lipsync-2-pro, veed/fabric-1.0, prunaai/p-video-avatar, heygen/lipsync-speed,
heygen/lipsync-precision, pixverse/lipsync, bytedance/omni-human, kwaivgi/kling-lip-sync,
wan-video/wan-2.2-s2v, bytedance/latentsync, плюс community-модели
(zsxkib/multitalk, tmappdev/lipsync на MuseTalk, cjwbw/sadtalker,
cjwbw/aniportrait-audio2vid, chenxwh/video-retalking).

Подтверждённые цены:

| Модель | Страница | Цена дословно |
|---|---|---|
| heygen/lipsync-speed | <https://replicate.com/heygen/lipsync-speed> | «Billed per second of output video at $0.0333/second» |
| heygen/lipsync-precision | <https://replicate.com/heygen/lipsync-precision> | «Billed per second of output video at $0.0667/second» |
| bytedance/latentsync | <https://replicate.com/bytedance/latentsync> | «This model costs approximately $0.099 to run on Replicate, or 10 runs per $1» |

Цены `bytedance/omni-human`, `sync/lipsync-2`, `sync/lipsync-2-pro`,
`kwaivgi/kling-lip-sync`, `pixverse/lipsync`, `wan-video/wan-2.2-s2v` со страниц
моделей вытащить не удалось — блок стоимости у официальных моделей отрисовывается
скриптом, а `replicate.com/pricing` перечисляет только Flux, Claude, DeepSeek и т. п.
Страница lipsync-2-pro прямо отсылает наружу: «Lipsync-2-Pro is available through
Replicate's usage-based pricing. For detailed pricing and plan requirements, visit
Sync Labs Pricing».

---

## Что подтвердить не удалось и почему

Ничего из перечисленного ниже я не заполнял догадками.

| Что | Почему |
|---|---|
| **Русский язык в липсинке — ни у одного провайдера** | Ни на одной официальной странице не нашёл списка языков с явным упоминанием русского. У HeyGen эндпоинт `/v3/video-translations/languages` возвращает список динамически, в документации он не напечатан. Synthesia пишет «over 160+ languages and accents» без списка. Hedra Character-3 — «full multi-language support» без перечня. **Проверять придётся вызовом API или тестовым роликом.** |
| Цены тарифов D-ID (Studio и API) | Страницы `/pricing/studio/` и `/pricing/api/` отдают только навигацию и футер — таблицы подгружаются скриптом. Статья справочного центра про подписки отвечает HTTP 403. Кредитная механика (1 кредит = до 15 с, округление вверх до 15 с) подтверждена, суммы — нет |
| Цены тарифов Argil в долларах | `argil.ai/pricing` отдаёт «Loading plans…» — тарифы рендерятся скриптом. Кредитные ставки из `docs.argil.ai` подтверждены, но курс «кредит → доллар» там не опубликован |
| Долларовая стоимость кредита Akool | На `akool.com/pricing` все планы отрисованы как «$0/seat/mo» — цифры подставляются скриптом. Кредитные ставки за секунду подтверждены, конвертация в доллары — нет |
| Что покупает кредит Captions / Mirage; наличие и цена API | Страница тарифов даёт суммы и число кредитов, но не курс «кредит → секунды видео». API на странице тарифов не упоминается вовсе |
| Что покупает кредит Creatify; цена API | Страница тарифов даёт суммы и число кредитов, но не курс. API помечен как Enterprise-only без цифр |
| Помесячные суммы Vidnoz | На странице тарифов вместо цен Starter и Business показан только баннер «25% OFF First Month». Кроме того, объёмы кредитов (15 и 30 в месяц) при опубликованной ставке 0.5 кредита/секунду дают 30 и 60 секунд в месяц — единицы на странице между собой не сходятся |
| Официальные цены Kling API | `klingai.com/global/dev/pricing` и страница ресурсных пакетов в `app.klingai.com` отвечают **HTTP 446** — доступ блокируется |
| Цены и ставка кредитов Higgsfield | `higgsfield.ai/pricing` отдаёт только шапку (тарифы грузятся скриптом), `cloud.higgsfield.ai` — страница-редирект, `higgsfield.ai/api` — 404 |
| Цена API Hedra за секунду | Документация не публикует ставку; она возвращается только эндпоинтом `POST /models/hedra-character-3/estimate`, для которого нужен ключ. Цифры Hedra в таблице выведены из подписочных кредитов (6 кредитов/с), а не из прайса API |
| Публичный прайс Runware по моделям | `runware.ai/pricing` не печатает цены по моделям: «pricing varies across thousands of parameters», предлагается открыть Playground. Страницы моделей показывают только примеры суммарной стоимости отдельных генераций. Использованы собственные замеры заказчика |
| Цены Replicate на omni-human, sync/lipsync-2 и -2-pro, kling-lip-sync, pixverse/lipsync, wan-2.2-s2v | Блок стоимости у официальных моделей отрисовывается скриптом; `replicate.com/pricing` этих моделей не содержит |
| Модели Sonic, EchoMimic, Hallo, FLOAT | На fal.ai по прямым слугам — 404, в каталоге липсинка Replicate и в каталоге аватар-моделей Segmind не перечислены. Публичной цены у крупных агрегаторов на август 2026 не нашёл |
| Wan-S2V на fal.ai | Слуг `fal-ai/wan-s2v` отвечает 404. На Replicate модель есть (`wan-video/wan-2.2-s2v`), но её цена скрыта скриптом |
| Реальная цена минуты InfiniteTalk на Segmind | Тарификация «за GPU-секунду» ($0.0043), а не за секунду видео. Без замера длительности прогона в минуты ролика не пересчитывается |
| Цена MuseTalk на fal.ai | На странице модели стоит плейсхолдер «Your request will cost $0 per compute second» — реальной ставки нет |
| Максимальная длина ролика у большинства моделей агрегаторов | На страницах моделей fal.ai и Segmind лимиты длины в основном не указаны. Явные лимиты нашлись только у OmniHuman на fal.ai (аудио ≤ 30 с) и Kling lipsync на fal.ai (видео 2–10 с, аудио 2–60 с) |

---

## Что проверить дальше

1. **Русский на HeyGen Avatar IV** — единственный реальный риск для варианта №1.
   Проверяется одним вызовом на 5 секунд за $0.25.
2. **Ставка API Hedra за секунду** через `POST /models/hedra-character-3/estimate` —
   если она окажется ниже $0.05/с, Hedra обгонит HeyGen и по цене, и по длине (10 мин),
   и по вертикали 9:16.
3. **Совмещается ли подписка HeyGen Creator с API.** Если да — $0.80–0.97 за минуту
   при полной автоматизации, что закрывает вопрос полностью.
4. **Pruna P Video Avatar на Segmind** ($0.03125/с в 720p) — надо посмотреть глазами,
   держит ли рот на уровне Avatar IV. Это самая дешёвая позиция среди «фото + звук».
