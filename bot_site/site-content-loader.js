// bot_site/site-content-loader.js
//
// Разовый скрипт для services.html. Он ничего не меняет во внешнем виде
// страницы — только подставляет актуальные текст/фото карточки услуги,
// которые владелица заливает через Telegram-бота.
//
// Как подключить (один раз, вручную, в репозитории my-lending-test):
// 1. Добавьте id="pilot-card-text" на элемент с описанием карточки услуги
//    (например "Принятие тела") и id="pilot-card-photo" на её <img>.
// 2. Перед закрывающим </body> на services.html добавьте:
//    <script src="site-content-loader.js" data-api-base="https://147-45-175-189.sslip.io"></script>

(function () {
  var scriptTag = document.currentScript;
  var apiBase = scriptTag.getAttribute("data-api-base");
  if (!apiBase) {
    return;
  }

  fetch(apiBase + "/content/services/card_1")
    .then(function (response) {
      if (!response.ok) {
        throw new Error("site content API returned " + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      var textElement = document.getElementById("pilot-card-text");
      if (textElement && data.text) {
        textElement.textContent = data.text;
      }

      var photoElement = document.getElementById("pilot-card-photo");
      if (photoElement && data.photo_path) {
        photoElement.src = apiBase + data.photo_path;
      }
    })
    .catch(function () {
      // API недоступен или сервер лежит — страница остаётся со своим
      // исходным (зашитым в HTML) текстом/фото, как и раньше. Сайт не
      // должен зависеть от бота для базовой работоспособности.
    });
})();
