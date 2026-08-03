// Переходник (proxy) к openrouter.ai на Cloudflare Workers.
//
// Зачем: openrouter.ai отвечает 403 на любые запросы с российских IP —
// блокируется даже главная страница и публичный список моделей, то есть дело
// не в ключе и не в аккаунте (проверено с двух серверов: Timeweb 31.07.2026 и
// Beget 03.08.2026). Cloudflare не блокируется, поэтому бот обращается к этому
// воркеру, а воркер уже ходит в OpenRouter.
//
// Как подключить в боте: в `.env` указать
//     AI_PROXY_BASE_URL=https://ИМЯ.ПОДДОМЕН.workers.dev/v1
//     AI_GATEWAY_PROVIDER=openrouter
// Путь после адреса воркера подставляется к https://openrouter.ai/api как есть,
// поэтому `/v1/chat/completions` уходит в `https://openrouter.ai/api/v1/chat/completions`.
//
// Про безопасность: ключ OpenRouter здесь НЕ хранится — он приходит в заголовке
// от бота и просто передаётся дальше. Поэтому чужой, нашедший адрес воркера, не
// сможет тратить ваши деньги: без своего ключа запрос отклонит сам OpenRouter.
// Запросы без заголовка Authorization воркер отбрасывает сам, чтобы его не
// использовали как анонимный обходной путь.

const UPSTREAM = "https://openrouter.ai/api";

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Проверка живости: открыть адрес воркера в браузере и увидеть "proxy ok".
    if (url.pathname === "/" || url.pathname === "") {
      return new Response("proxy ok\n", {
        status: 200,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    // Список моделей у OpenRouter публичный. Разрешаем его без ключа, чтобы
    // доступность переходника можно было проверить, ещё не заводя ключ на
    // сервере.
    const isPublicModelList = request.method === "GET" && url.pathname === "/v1/models";

    if (!isPublicModelList && !request.headers.get("authorization")) {
      return new Response(
        JSON.stringify({ error: { message: "Authorization header required", code: 403 } }),
        { status: 403, headers: { "content-type": "application/json" } },
      );
    }

    const headers = new Headers(request.headers);
    // Host должен принадлежать получателю, иначе OpenRouter не узнает свой домен.
    headers.delete("host");

    const hasBody = request.method !== "GET" && request.method !== "HEAD";

    const upstreamResponse = await fetch(UPSTREAM + url.pathname + url.search, {
      method: request.method,
      headers,
      // Тело передаётся потоком: через этот же путь идут загрузки аудио для
      // расшифровки, их нельзя буферизовать целиком без нужды.
      body: hasBody ? request.body : undefined,
    });

    // Ответ отдаём как есть — и заголовки, и код. Бот сам разбирает 402
    // (кончились деньги), 429 (лимит частоты) и тела ошибок.
    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: upstreamResponse.headers,
    });
  },
};
