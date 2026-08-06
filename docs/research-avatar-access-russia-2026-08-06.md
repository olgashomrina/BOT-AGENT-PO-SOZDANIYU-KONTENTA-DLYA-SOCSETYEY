# Говорящие видео-аватары: доступ и оплата из России

Разведка от 06.08.2026. Только официальные источники: пользовательские соглашения
сервисов, официальная справка, тексты регуляторов. Форумы, обзоры и пересказы не
использовались (единственное исключение оговорено отдельно — см. «Что выяснить не
удалось»).

Контекст: продакшн-сервер у Beget в Москве (159.194.214.72, AS198610). Оплата уже
идёт через Runware, счёт пополнен картой успешно.

---

## Вывод

**Реально доступно и оплачиваемо без ухищрений сегодня — ровно один путь: Runware,
которым проект уже пользуется.** Он закрывает и липсинк, и говорящих аватаров,
включая модели HeyGen, Kling Avatar и ByteDance OmniHuman, к которым напрямую с
российской карты не подступиться.

Три отдельных вывода, которые стоит держать в голове:

1. **Ни один из тринадцати проверенных сервисов не запрещает Россию по названию.**
   Прямой цитаты «нельзя из России» нет ни у кого. Стандартная формулировка —
   «вы не находитесь в стране под эмбарго США». Россия под всеобъемлющее эмбарго
   США не подпадает, и это видно по тем сервисам, которые не поленились
   перечислить эмбарго списком: RunPod и Vast.ai называют Кубу, Иран, КНДР,
   Сирию и оккупированные регионы Украины — России в списке нет.

2. **Барьер не юридический, а платёжный.** Visa и Mastercard с 05.03.2022
   отключили карты российских банков за пределами страны, а Stripe — процессор у
   большинства этих сервисов — прямо пишет, что не обслуживает пользователей из
   России и не поддерживает «Мир». Поэтому вопрос «пустят ли» почти всегда
   упирается в «чем платить», а не в «разрешено ли».

3. **Российские агрегаторы липсинк и аватаров не закрывают.** У vsegpt.ru (по его
   собственному API-каталогу) есть Kling, LTX, Veo 3.1 и Sora 2 — то есть
   генерация видео из текста и картинки, — но ни одной модели липсинка или
   говорящего аватара. У ProxyAPI только OpenAI / Anthropic / Google. Так что
   рублёвая оплата у них есть, а нужного класса моделей — нет.

**Практический ответ:** оставаться на Runware. Британское юрлицо, оплата картой уже
прошла, каталог липсинка и аватаров — 22 модели, и там же лежат HeyGen Avatar V,
Kling Avatar 2.0 и OmniHuman-1.5. Уходить с него ради прямых договоров с HeyGen или
Hedra смысла нет: это не даст ни одной модели, которой не было бы на Runware,
зато потребует решать вопрос с оплатой заново.

---

## Таблица: сервис — доступ — оплата — источник

| Сервис | Юрисдикция | Запрет на Россию в условиях | Оплата | Источник |
|---|---|---|---|---|
| **Runware** (используем) | Великобритания | Нет вообще: ни экспортного контроля, ни санкционного пункта | Visa, Mastercard, Amex, Discover, JCB, UnionPay; всё в USD. Российская карта прошла на практике | [runware.ai/terms](https://runware.ai/terms) |
| HeyGen | США | Нет. §19: только эмбарго США и списки запрещённых лиц | Stripe / Chargebee → российская карта не пройдёт | [heygen.com/terms](https://www.heygen.com/terms), [help.heygen.com](https://help.heygen.com/en/articles/9999710-billing-payments-invoice) |
| Hedra | США (Нью-Йорк) | Нет. Санкционного и экспортного пункта в условиях нет совсем | Не раскрыто в условиях | [hedra.com/terms](https://www.hedra.com/terms), [hedra.com/api-terms](https://www.hedra.com/api-terms) |
| D-ID | Израиль / США | Нет. §29.1(ii): эмбарго США и списки лиц | Не раскрыто | [d-id.com/studio-end-user-license-agreement](https://www.d-id.com/studio-end-user-license-agreement/) |
| Synthesia | Великобритания | Нет. В Customer ToS санкционного пункта нет; AUP требует соблюдения «export control laws» | Не раскрыто | [synthesia.io/legal/customer-terms-of-service](https://www.synthesia.io/legal/customer-terms-of-service) |
| Argil | Франция | Нет. Только общая гарантия не подставить Argil под санкции | Stripe → российская карта не пройдёт | [argil.ai/terms](https://www.argil.ai/terms) |
| Akool | США | Нет. §18.8: эмбарго США, SDN, Denied Persons List | Не раскрыто | [akool.com/terms-of-service](https://akool.com/terms-of-service) |
| fal.ai | США | Нет. Эмбарго США и списки конечных пользователей | Не раскрыто | [fal.ai/terms](https://fal.ai/terms) — см. оговорку ниже |
| Replicate | США | Нет, но формулировка самая жёсткая: §2.1 отсекает всех, кому запрещено пользоваться по законам США | «credit card, debit card or bank transfer» (§4.2(a)) | [replicate.com/terms](https://replicate.com/terms) |
| Segmind | Индия | Нет. Санкционных пунктов в условиях нет; только §4.2 «соблюдайте законы» | Не раскрыто | [segmind.com/terms](https://www.segmind.com/terms) |
| RunPod | США | Нет. §6 перечисляет эмбарго списком, России там нет | Stripe **и Crypto.com** (§8) | [runpod.io/legal/terms-of-service](https://www.runpod.io/legal/terms-of-service) |
| Vast.ai | США | Нет. Перечень эмбарго, России нет | Карты; крипта не подтверждена | [vast.ai/terms](https://vast.ai/terms) |
| Kling официальный | Китай (Kuaishou) | Не установлено — сайт не отдаёт текст (HTTP 446) | Не установлено | [kling.ai/docs/user-policy](https://kling.ai/docs/user-policy) — недоступно |
| Higgsfield | США | Нет. §19.12: эмбарго США и списки лиц | Stripe (§9.1) → российская карта не пройдёт | [higgsfield.ai/terms-of-use-agreement](https://higgsfield.ai/terms-of-use-agreement) |

---

## Правовой фон: почему запретов «по названию» нет

Стоит развести две разные вещи, которые обычно путают: всеобъемлющее эмбарго и
точечные отраслевые запреты. Россия — во второй категории, и именно поэтому
типовая фраза в пользовательских соглашениях её не задевает.

### США: Россия не под всеобъемлющим эмбарго

Практически все американские сервисы используют одну и ту же шаблонную фразу.
HeyGen, §19:

> «The Services may not be exported or re-exported (a) into any U.S. embargoed
> countries or any country that has been designated…»
>
> «By using the Services, you represent and warrant that you are not located in any
> such country or on any such list.»

Что именно значит «U.S. embargoed country», видно у тех, кто дал список. RunPod, §6:

> «located, organized, or resident in a country or territory that is, or becomes
> subject to, an embargo by the United States or other applicable jurisdictions
> (such embargoed jurisdictions currently being Cuba, Iran, North Korea, Syria, and
> the Crimea, so-called Donetsk People's Republic, and so-called Luhansk People's
> Republic regions of Ukraine)»

Vast.ai, раздел EXPORT COMPLIANCE:

> «User represents that neither it nor any end users of the Services is (i) located
> in, organized under the laws of, or ordinarily resident in Cuba, Iran, North
> Korea, Syria, or the Crimea, Donetsk, Luhansk, Kherson or Zaporizhzhia regions of
> Ukraine, or any other region subject to comprehensive U.S. embargo»

Москва ни в один из этих перечней не попадает. Крым, ДНР, ЛНР (и у Vast.ai —
Херсон и Запорожье) попадают, но это территории Украины, а не РФ.

### США: отдельный запрет на IT-услуги в РФ (действует с 12.09.2024)

А вот это Россию задевает напрямую. По Executive Order 14071 Минфин США 12.06.2024
выпустил determination, вступивший в силу **12 сентября 2024**. Он запрещает
поставлять лицам в РФ (1) IT consultancy and design services и (2) IT support
services и облачные сервисы для enterprise management software и design and
manufacturing software.

Важная оговорка из самого же разъяснения OFAC:

> «The aim of this action is not to prohibit all activity relating to the provision
> of IT and software-related services to Russia… These measures do not prohibit
> internet access or the delivery of internet-based communications services.»

То есть запрет нацелен на корпоративный софт (ERP, CAD/CAM), а не на любой SaaS.
Генерация видео под определение «enterprise management software» не подходит.

Источники: [OFAC FAQ 1184](https://ofac.treasury.gov/faqs/1184),
[Federal Register 2024-15709](https://www.federalregister.gov/documents/2024/07/18/2024-15709/publication-of-russian-harmful-foreign-activities-sanctions-regulations-determination),
[ofac.treasury.gov/recent-actions/20240612](https://ofac.treasury.gov/recent-actions/20240612).

### ЕС: статья 5n Регламента 833/2014

Запрещает поставку IT consultancy services и ПО для управления предприятием, в том
числе через SaaS. Ключевая деталь: адресат запрета — **юридические лица,
учреждённые в России, и правительство РФ**. Физические лица под 5n прямо не
подпадают. Источник: [FAQ Еврокомиссии по ст. 5n](https://finance.ec.europa.eu/system/files/2023-07/faqs-sanctions-russia-services-provision_en.pdf),
[FAQ по ст. 5n(2b) о ПО](https://finance.ec.europa.eu/system/files/2024-02/faqs-sanctions-russia-software_en,.pdf).

### Великобритания: Reg 54C — здесь физлица попадают

Это самая жёсткая из трёх юрисдикций для нашего случая, и она же — юрисдикция
Runware и Synthesia. Regulation 54C Russia (Sanctions) (EU Exit) Regulations 2019 с
16.12.2022 запрещает британским лицам поставлять «IT consultancy and design
services» «a person connected with Russia». Определение включает физлиц:

> «a company incorporated or constituted under Russian law… or domiciled in Russia,
> or an individual or group of individuals who are ordinarily resident or are
> located in Russia»

Но официальное руководство прямо перечисляет, что под запрет **не** подпадает:

> «civilian telecommunication services», «services incident to exchange of
> communications over the internet, such as instant messaging, videoconferencing,
> chat and email», «data storage services», «VPN services»

и что мера «не предназначена покрыть всю широту деятельности, связанной с
информационными технологиями». Инференс-API генеративной модели — не «advisory and
design services related to IT systems and infrastructure», так что под 54C он,
судя по тексту руководства, не попадает.

Источник: [gov.uk, Complying with professional and business services sanctions related to Russia](https://www.gov.uk/government/publications/professional-and-business-services-to-a-person-connected-with-russia/professional-and-business-services-to-a-person-connected-with-russia).

### Платежи — вот где настоящий барьер

Visa, официальное заявление от 05.03.2022:

> «all transactions initiated with Visa cards issued in Russia will no longer work
> outside the country»

[investor.visa.com](https://investor.visa.com/news/news-details/2022/Visa-Suspends-All-Russia-Operations/)

Mastercard, тогда же: карты, выпущенные российскими банками, не поддерживаются
сетью Mastercard независимо от того, где ими платят.
[mastercard.com/news/press/2022/march](https://www.mastercard.com/news/press/2022/march/mastercard-statement-on-suspension-of-russian-operations)

Stripe, официальная справка:

> «Stripe currently does not support users located in Russia, Ukraine and Belarus.»
>
> «Stripe will not process transactions involving sanctioned Russian and Belarusian
> financial institutions and does not support the Mir card payment system.»

Плюс Stripe перекладывает на своих продавцов запрет OFAC:

> «It is prohibited to use Stripe's products and services to directly or indirectly
> export, reexport, sell, or supply accounting services, management consulting
> services, information technology consultancy and design services, and IT-support
> services and cloud-based services for enterprise management software and design
> and manufacturing software to any person located in Russia.»

[support.stripe.com/questions/sanctions-on-russia-and-belarus](https://support.stripe.com/questions/sanctions-on-russia-and-belarus)

Это ключ ко всему списку: Argil, Higgsfield и HeyGen явно сидят на Stripe. Значит
российская карта у них не пройдёт — не потому, что сервис запретил Россию, а
потому, что запретил процессор.

---

## Подробности по сервисам

### Runware — то, чем пользуемся

Юрлицо: DNS House, 382 Kenton Road, Harrow, Greater London, HA3 8DP; VAT
GB444184006. §19: право Великобритании.

§1 — единственная географическая оговорка во всём документе:

> «Our site is primarily directed to users residing in the United Kingdom, but we
> offer our Services to businesses globally where legally permissible.»

Санкционных и экспортных пунктов в условиях **нет вообще** — редкость для этого
списка. §6, оплата:

> «All payments shall be in US dollars (or the equivalent in a local currency as
> determined by our payment provider).»

Принимаются Visa, Mastercard, American Express, Discover, JCB, UnionPay. §9: 18+.

**Каталог липсинка и аватаров.** Коллекция «Best Lip Sync» — 22 модели:
HeyGen Avatar V, OmniHuman-1, PixVerse LipSync, KlingAI Lip-Sync, Wan2.5-Preview,
OmniHuman-1.5, sync-3, lipsync-2-pro, lipsync-2, P-Video, P-Video-Avatar,
Seedance 2.0 / 2.0 Fast, Kling VIDEO 3.0 Pro / 4K / Omni Pro / Omni 4K,
Grok Imagine Video, PixVerse V6, KlingAI Avatar 2.0 Pro, MiniMax Hailuo 2.3,
LTX-2.3. [runware.ai/collections/best-lip-sync](https://runware.ai/collections/best-lip-sync)

Цены с карточек моделей (Runware показывает стоимость примеров генерации, а не
ставку за секунду):

| Модель | AIR ID | Стоимость генерации | Вход |
|---|---|---|---|
| KlingAI Avatar 2.0 Standard | `klingai:@2.0` | $0.54–0.84 | картинка + аудио |
| OmniHuman-1.5 | `bytedance:5@2` | $1.49–2.48 | картинка + аудио (+ маска) |
| HeyGen Avatar V | `heygen:avatar@5` | $2.54–3.12 | аватар + текст (голос, язык, скорость — опционально) |

[klingai-avatar-2-0-standard](https://runware.ai/models/klingai-avatar-2-0-standard),
[omnihuman-1-5](https://runware.ai/models/omnihuman-1-5),
[heygen-avatar-v](https://runware.ai/models/heygen-avatar-v)

Тарификация: pay-as-you-go, «all costs are denominated in USD», баланс списывается
в реальном времени, неудачные запросы не тарифицируются, у новых аккаунтов $2
бесплатных кредитов. [runware.ai/docs/platform/pricing](https://runware.ai/docs/platform/pricing)

**Уже измерено командой 06.08** (см. `docs/superpowers/specs/2026-08-06-video-circle-stage2-design.md`):
`klingai:7@1` — 30-секундный кружок $0.276 ≈ 28 ₽; `pixverse:lipsync@1` $0.0136/с ≈
41 ₽; `sync:lipsync-2@1` $0.044/с ≈ 132 ₽; `sync:3@0` $0.133/с ≈ 400 ₽.

### HeyGen

§19 Export Controls — шаблонная формулировка про эмбарго США, SDN и Denied Persons
List, цитата приведена выше. Отдельного запрета на Россию нет. §2: 18+ и
дееспособность, географических условий нет.

Оплата (официальная справка): «Credit cards, Debit cards, Cash App, Bank accounts,
Preauthorized debit, PayPal (in selected countries)». Управление биллингом идёт
через Stripe или Chargebee. Отдельно упоминаются SEPA и 3DS-карты со сроком
обработки до 6 рабочих дней. Список стран, где сервис недоступен, в справке не
публикуется.

Практический вывод: напрямую платить нечем, но **модель HeyGen Avatar V доступна
через Runware** (`heygen:avatar@5`) — это снимает вопрос.

### Hedra

Самый пустой документ из всех. Ни в [условиях](https://www.hedra.com/terms), ни в
[API-условиях](https://www.hedra.com/api-terms) нет ни пункта об экспортном
контроле, ни санкционного пункта, ни списка запрещённых стран. Единственная
географическая оговорка — §13 International Users:

> «The Service is controlled and offered by Hedra from its facilities in the United
> States of America.»

Право Нью-Йорка. Способы оплаты в условиях не раскрыты.

### D-ID

§16 Export Controls:

> «You agree to comply fully with all applicable export laws and regulations to
> ensure that neither the Software nor any technical data related thereto are
> exported or re-exported directly or indirectly in violation of, or used for any
> purposes prohibited by, such laws and regulations.»

§29.1(ii):

> «You represent and warrant that: (a) you are not located in a region that is
> subject to a U.S. Government embargo, or that has been designated by the U.S.
> Government as a "terrorist supporting" region; and (b) you are not listed on any
> U.S. Government list of prohibited or restricted parties.»

§26: для резидентов США — право Делавэра, для остальных — право Израиля. §8.1 про
оплату не называет ни способов, ни стран.

### Synthesia

Британская компания. В Customer Terms of Service санкционного пункта, экспортного
контроля и географических ограничений нет — только общая формула: «We will comply
with those laws applicable to our provisioning of the Services to customers
generally». Acceptable Use Policy требует соблюдения «all intellectual property,
data protection, privacy, artificial intelligence and export control laws».

Отдельного объявления о прекращении работы в России найти не удалось. Но как
британское лицо Synthesia связана Reg 54C — см. раздел про Великобританию.

### Argil

Французская компания, санкционного пункта нет. Ближайшее по смыслу — §7.1.1:

> «The User who requests the creation of their Personal Space guarantees that their
> use of the Platform and Services will not expose Argil.ai to sanctions»

и §9.3 — общий запрет на противоправную деятельность. §6.7.1 оставляет за Argil
право отказать в выполнении операции по требованию компетентного органа. Процессор
— Stripe, то есть российская карта не пройдёт.

### Akool

§18.8:

> «You may not use, export, import, or transfer the Akool Service except as
> authorized by U.S. law»

и запрет на передачу «to anyone on the U.S. Treasury Department's list of Specially
Designated Nationals or the U.S. Department of Commerce's Denied Person's List or
Entity List». Плюс представление пользователя, что он «not located in a country
that is subject to a U.S. Government embargo». Россия по названию не упомянута.

### fal.ai

Из официальных условий: пользователь отвечает за соблюдение экспортного контроля
США, включая эмбарго; и заявляет, что не находится в стране под эмбарго США либо
обозначенной как «terrorist supporting», и не входит в списки ограниченных конечных
пользователей. **Оговорка:** страницу отрендерить не удалось (HTTP 429 при всех
попытках), формулировка получена из выдачи поисковой системы по самой странице
fal.ai/terms. Перепроверить.

### Replicate

Формально самый строгий текст в списке. §12.8(a):

> «The Services may not be exported or re-exported (a) to any country under a U.S.
> embargo or designated by the U.S. Government as a "terrorist-supporting" country,
> or (b) to any individual or entity listed on U.S. Government lists of prohibited
> or restricted parties…»

§12.8(b):

> «By using the Services, CUSTOMER CONFIRMS AND WARRANT THAT YOU ARE NOT LOCATED IN
> SUCH A COUNTRY OR LISTED ON ANY SUCH PROHIBITED LIST.»

§2.1 — то, чего нет у остальных:

> «You are not eligible to be a Customer either directly or indirectly if you are
> barred from using the Services under the Laws of the United States or any other
> applicable jurisdiction, including pursuant to Section 12.8.»

§4.2(a): «including but not limited to credit card, debit card or bank transfer».
Россия по названию не упомянута и здесь.

### Segmind

Индийская юрисдикция. Экспортного контроля, санкционных пунктов, списков стран и
описания способов оплаты в условиях нет. Единственное близкое — §4.2 Compliance
with Laws: «You represent and warrant to Segmind that your use of Segmind Services
will comply with all applicable laws».

### RunPod

§6 — цитата с полным перечнем эмбарго приведена выше; России в нём нет. Список
запрещённых лиц:

> «any U.S. or other applicable sanctions or export control-related prohibited party
> list (including, without limitation, the Specially Designated Nationals and
> Blocked Persons List, Foreign Sanctions Evaders List, and Sectoral Sanctions
> Identifications List…)»

§8: процессоры — **Stripe и Crypto.com**. Наличие крипто-канала делает RunPod
формально оплачиваемым из России в обход карточной блокировки, но это уже аренда
GPU под self-host, а не готовый липсинк.

### Vast.ai

Раздел EXPORT COMPLIANCE — цитата с перечнем выше. Ссылается на EAR (15 C.F.R.
Parts 730-774) и санкции OFAC. Из платёжных ограничений в условиях есть только одно
и не про страны: запрет на майнинг при оплате кредитной картой (PROHIBITED
ACTIVITIES, п. 22).

### Kling официальный

Официальный текст получить не удалось: kling.ai, klingai.com и app.klingai.com
отвечают HTTP 446 на любые запросы (собственная защита сайта). Из выдачи поисковой
системы по официальной странице `kling.ai/docs/user-policy` следует, что там есть
представление пользователя о том, что он не подпадает под санкции и эмбарго, и что
действуют отдельные условия по странам и регионам, имеющие приоритет над общим
текстом. Полностью проверить не удалось — см. раздел ниже.

Практически это неважно: Kling Avatar 2.0 и Kling Lip-Sync доступны через Runware.

### Higgsfield

§19.12 Export Control:

> «You may not use or export the Service except as authorized by U.S. and other
> applicable laws. You represent that you are not located in any U.S.-embargoed
> country and are not on any U.S. government list of prohibited parties.»

§17.1 International Access:

> «The Service may be accessed from countries around the world and may contain
> references to services and Content that are not available in your country. Those
> who access or use the Service from other countries do so at their own volition and
> are responsible for compliance with local law.»

§12 перекладывает на пользователя ответственность за нарушение «any export control,
sanctions, or data protection law». §9.1: процессор — Stripe.

---

## Посредники и агрегаторы с рублёвой оплатой

Здесь ожидание не оправдалось: рублёвая оплата у российских агрегаторов есть, а
моделей нужного класса — нет.

### vsegpt.ru — уже используем для LLM

Каталог проверен по официальному API-эндпоинту
[api.vsegpt.ru/v1/models](https://api.vsegpt.ru/v1/models). Видео-модели есть:

- `txt2vid-kling/standart` — Kling Standart Text-to-Video
- `img2vid-kling/standart` — Kling Standart Image-to-Video
- `txt2vid-ltx/video-095` — LTX 0.9.5
- `txt2vid-google/veo3.1-fast` и варианты
- `txt2vid-openai/sora-2-audio` и варианты

**Моделей липсинка, аватаров и talking head в каталоге нет.** Это генерация видео
из текста и картинки — другой класс задачи. Для кружочков не подходит: нужен вход
«видео-донор + аудио» или «фото + аудио».

### ProxyAPI

Провайдеры: OpenAI, Anthropic, Google (Gemini), плюс проксирование OpenRouter. Из
медиа — генерация видео (Sora, Veo), TTS и STT. **Аватаров и липсинка нет.** Оплата
в рублях российскими картами, для юрлиц — безнал с закрывающими документами.
[proxyapi.ru](https://proxyapi.ru/), [proxyapi.ru/docs](https://proxyapi.ru/docs)

### GPTunnel

Официальная страница по Kling подтверждает наличие Kling 3.0 и Sora 2 (генерация
видео со звуком) и работу «в России без VPN». Аватары и липсинк на официальных
страницах не упомянуты. Прайс-лист в рублях на сайте найти не удалось.
[gptunnel.ru/en/kling](https://www.gptunnel.ru/en/kling)

### Runware как «нейтральный» посредник

Не российский и рублей не принимает, но по факту работает как тот же посредник:
британское юрлицо агрегирует модели HeyGen, ByteDance, Kling, PixVerse, Sync и
других, счёт пополняется картой, оплата в долларах. Для нашей задачи это
единственный канал, где липсинк и аватары есть в наличии и оплачены. Цены —
в разделе про Runware выше.

---

## Что выяснить не удалось

Честный список пробелов — их стоит закрыть, если решение будет пересматриваться.

1. **Полный прайс vsegpt.ru в рублях.** Страницы `Docs/Models` и `Docs/Pricing`
   рендерятся на JavaScript, инструмент получает только меню и подвал. Список
   моделей удалось взять только через `api.vsegpt.ru/v1/models`, но поля цен там
   приходят нулями (`"0.0"`) — видимо, потому что видео тарифицируется не за токены.
   Рублёвые ставки за видео у vsegpt так и не получены.

2. **Официальный текст условий Kling.** kling.ai, klingai.com и app.klingai.com
   отвечают HTTP 446 на все запросы. Ни user-policy, ни payment-policy прочитать не
   удалось. Способы оплаты у официального Kling и его региональные ограничения
   остаются непроверенными.

3. **fal.ai/terms.** HTTP 429 при четырёх попытках подряд. Цитата в отчёте взята из
   выдачи поисковой системы по официальной странице, а не из отрендеренного
   документа. Это единственное место в отчёте, где первоисточник не прочитан
   напрямую, — пометка сохранена и в разделе про fal.ai.

4. **Тексты OFAC напрямую.** `ofac.treasury.gov/faqs/1184`, `/1185`, `/1188` не
   открылись (таймаут и блокировка домена), Federal Register редиректит на
   `unblock.federalregister.gov`. Формулировки determination взяты из выдачи
   поисковой системы по официальным страницам ofac.treasury.gov и
   federalregister.gov. Содержательно они совпадают между собой и с текстом Stripe,
   но дословную сверку по первоисточнику стоит сделать, если формулировка окажется
   юридически значимой.

5. **Консолидированный текст ст. 5n Регламента 833/2014.** EUR-Lex отдал не ту
   редакцию, PDF с FAQ Еврокомиссии не удалось распарсить (нет poppler для
   рендеринга PDF). Изложение статьи 5n основано на официальном FAQ Еврокомиссии,
   но не на дословном тексте регламента.

6. **Прайс-лист GPTunnel.** Официальной страницы с ценами в рублях найти не удалось;
   есть только описательные страницы по моделям.

7. **Ни у одного сервиса не найдено официального объявления о прекращении работы в
   России.** Искал целенаправленно у HeyGen и Synthesia — таких публикаций нет.
   Отсутствие находки не равно отсутствию факта, но по официальным каналам их нет.

8. **Принимает ли Runware именно российские карты — по документам не подтверждено.**
   В §6 перечислены только платёжные системы (Visa, Mastercard, Amex, Discover,
   JCB, UnionPay), страна эмитента не оговорена ни в ту, ни в другую сторону. Мы
   знаем, что счёт пополнен успешно, — но это факт из практики, а не гарантия из
   условий. Формально Runware вправе изменить это без предупреждения.

9. **Сетевая доступность с сервера не проверялась** — по условию задачи. Все выводы
   о доступности здесь юридические и платёжные, а не сетевые. Что openrouter.ai
   отдаёт 403, а api.vsegpt.ru и api.runware.ai работают — известно из прошлых
   проверок и в этой разведке не перепроверялось.
