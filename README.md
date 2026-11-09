Location Popularity Map API

REST API на Django REST Framework для сервісу, де користувачі додають цікаві локації, залишають відгуки з оцінками та переглядають найпопулярніші місця. Рейтинг і популярність не зберігаються в базі: вони обчислюються в ORM під час кожного запиту на основі активності користувачів.

Можливості
Аутентифікація через Django Session + Cookies (без JWT): реєстрація, вхід, вихід, скидання пароля через email
CRUD категорій і локацій, soft delete локацій, розмежування прав (автор або адміністратор)
Відгуки з рейтингом 1-5 (один відгук на користувача до локації), like/dislike до відгуків
Рейтинг і популярність, обчислені через annotate
Лічильник переглядів з обмеженням «один раз на годину» на Redis
Пошук, фільтрація, сортування, пагінація
Кешування списку локацій у Redis з автоматичною інвалідацією
Експорт списку у JSON і CSV (pandas)
Email-сповіщення автору локації та підписникам про нові відгуки
OpenAPI-документація (Swagger UI)   
Стек

Python 3.12, Django 5.2, Django REST Framework, PostgreSQL 16, Redis 7, django-filter, pandas, drf-spectacular, Docker Compose.

Швидкий старт

Потрібні Docker та Docker Compose.

bash
git clone https://github.com/<username>/location-map.git
cd location-map
cp .env.example .env        # PowerShell: Copy-Item .env.example .env
docker compose up --build

Міграції застосовуються автоматично під час старту контейнера web. Щоб отримати доступ до адмінки та керувати категоріями, створіть суперкористувача:

bash
docker compose exec web python manage.py createsuperuser
Адреса	Призначення
http://localhost:8000/api/	API
http://localhost:8000/api/docs/	Swagger UI
http://localhost:8000/api/schema/	OpenAPI-схема
http://localhost:8000/admin/	Адмінка Django

Зупинка: docker compose down. Разом із видаленням даних БД: docker compose down -v.

Конфігурація

Усі налаштування беруться зі змінних оточення (файл .env, шаблон у .env.example).

Змінна	Опис
DJANGO_SECRET_KEY	секретний ключ Django
DJANGO_DEBUG	1 для режиму налагодження
DJANGO_ALLOWED_HOSTS	дозволені хости через кому
POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD	параметри бази даних
POSTGRES_HOST, POSTGRES_PORT	адреса бази (у compose: db, 5432)
REDIS_URL	адреса Redis, наприклад redis://redis:6379/1
DEFAULT_FROM_EMAIL	відправник листів

У режимі розробки листи не надсилаються, а виводяться в консоль контейнера (EMAIL_BACKEND = console). Переглянути їх: docker compose logs web.

API

Повний опис запитів і відповідей доступний у Swagger UI. Нижче коротка довідка.

Аутентифікація і CSRF

Сесійна аутентифікація потребує CSRF-токен для небезпечних методів (POST, PUT, PATCH, DELETE). Порядок роботи:

Увійти через POST /api/auth/login/ (cookie sessionid встановиться автоматично).
Отримати токен: GET /api/auth/csrf/ (повертає csrfToken і виставляє cookie csrftoken). Після входу токен змінюється, тому запитувати його варто вже після логіну.
Передавати значення в заголовку X-CSRFToken у всіх запитах, що змінюють дані.

Публічні ендпоінти (register, login, password-reset) не вимагають CSRF-токена. На них діє обмеження 10 запитів на хвилину з однієї IP-адреси.

Ендпоінти
Метод	URL	Доступ	Опис
GET	/api/auth/csrf/	усі	CSRF-токен
POST	/api/auth/register/	усі	реєстрація, одразу створює сесію
POST	/api/auth/login/	усі	вхід
POST	/api/auth/logout/	авторизовані	вихід
GET	/api/auth/me/	авторизовані	поточний користувач
POST	/api/auth/password-reset/	усі	запит на скидання пароля
POST	/api/auth/password-reset/confirm/	усі	встановлення нового пароля (uid, token, new_password)
GET	/api/categories/, /api/categories/{id}/	усі	список і деталі категорій
POST, PUT, PATCH, DELETE	/api/categories/...	адміністратор	керування категоріями
GET	/api/locations/	усі	список (пошук, фільтри, сортування, пагінація)
POST	/api/locations/	авторизовані	створення локації
GET	/api/locations/{id}/	усі	деталі, зараховує перегляд
PUT, PATCH, DELETE	/api/locations/{id}/	автор або адміністратор	зміна, soft delete
GET	/api/locations/export/	усі	експорт (file_format=json або csv)
GET	/api/locations/{id}/reviews/	усі	відгуки локації
POST	/api/locations/{id}/reviews/	авторизовані	створення відгуку
GET, PUT, PATCH, DELETE	/api/reviews/{id}/	читання всі, зміна автор або адміністратор	відгук
POST, DELETE	/api/reviews/{id}/vote/	авторизовані	like/dislike, зняття голосу
POST, DELETE	/api/locations/{id}/subscribe/	авторизовані	підписка на сповіщення, скасування
Коди відповідей, на які варто звернути увагу
Ситуація	Код
Повторний відгук до тієї самої локації	409 Conflict
Видалення категорії, у якій є локації	409 Conflict
Голосування за власний відгук	403 Forbidden
Рейтинг поза діапазоном 1-5, некоректні координати	400 Bad Request
Видалена (soft delete) локація	404 Not Found
Перевищено ліміт запитів на auth-ендпоінти	429 Too Many Requests
Параметри списку локацій
Параметр	Опис
search	пошук за назвою та описом
category	id категорії
author, author_username	id або ім'я автора
min_rating, max_rating	межі середнього рейтингу
ordering	created_at, avg_rating, popularity; префікс - для спадання
page	номер сторінки (10 записів на сторінці)

Параметри працюють і в /api/locations/export/, який повертає всі підходящі записи без пагінації.

Як це працює
Рейтинг і популярність

Обчислюються у locations/selectors.py одним SQL-запитом через annotate:

popularity = avg_rating * 10 + reviews_count * 3 + views_7d * 1

avg_rating для локації без відгуків вважається нулем. Переглади за 7 днів рахуються підзапитом, щоб JOIN із відгуками не множив рядки. Ваги винесені в константи на початку модуля. Під час сортування за рейтингом локації без відгуків потрапляють у кінець списку.

Переглади

Перегляд зараховується під час GET /api/locations/{id}/, але не частіше ніж раз на годину для одного глядача: авторизованого визначає user.pk, анонімного IP-адреса. Контроль виконує Redis через cache.add (операція SET NX), тому одночасні запити не можуть зарахувати перегляд двічі. Кожен зарахований перегляд зберігається в таблиці LocationView, з якої рахується views_7d.

Кешування списку

Відповідь GET /api/locations/ кешується в Redis на 5 хвилин. Ключ містить версію кешу та хеш усіх параметрів запиту (фільтри, сторінка, сортування). Сигнали post_save і post_delete для Location, Review та Category збільшують версію після коміту транзакції (transaction.on_commit), і всі старі ключі стають недійсними одразу. Такий підхід не потребує пошуку й видалення ключів за маскою.

Soft delete

Location.objects повертає лише активні записи, Location.all_objects усі. Метод delete() на об'єкті та на QuerySet лише виставляє is_deleted і deleted_at. Фізичне видалення доступне через hard_delete().

Сповіщення

Після створення відгуку автор локації та всі підписники отримують листа (крім автора відгуку). Лист надсилається після коміту транзакції, помилка пошти не впливає на відповідь API.

Експорт

GET /api/locations/export/?file_format=csv або json. Дані перетворюються через pandas. CSV зберігається в UTF-8 з BOM і комою як роздільником. Для відкриття в Excel з українською локалізацією: Дані, З тексту/CSV, роздільник «Кома».

Структура проєкту
config/               налаштування, головний urls.py
  settings.py
  settings_test.py    налаштування для тестів (in-memory кеш, швидкий хешер паролів)
accounts/             аутентифікація
  serializers.py
  services.py         відправка листа зі скиданням пароля
  views.py
locations/
  models.py           Category, Location, Review, ReviewVote, LocationView, LocationSubscription
  serializers.py
  selectors.py        запити до БД: анотації рейтингу й популярності
  services.py         облік переглядів
  cache.py            ключі й версіонування кешу
  signals.py          інвалідація кешу, сповіщення
  notifications.py    листи про нові відгуки
  exports.py          побудова JSON/CSV через pandas
  filters.py          django-filter
  permissions.py
  views.py
  tests/test_api.py

Основний принцип: в'юхи тонкі, запити до БД зібрані в selectors, бізнес-логіка в services, побічні ефекти (кеш, листи) в signals.

Тестування
bash
docker compose exec web python manage.py test --settings=config.settings_test

Набір із 22 API-тестів покриває аутентифікацію, права доступу, soft delete, унікальність відгуків і голосів, розрахунок рейтингу та популярності, ліміт переглядів, фільтри, пагінацію, інвалідацію кешу, експорт, підписки та листи. Для тестів Redis замінюється на LocMemCache, тому вони не змінюють дані розробницького середовища. База даних потрібна (піднімається разом із compose).

Рішення та припущення
Категорії створює, змінює й видаляє лише адміністратор: завдання не уточнює, хто ними керує.
Повторний like/dislike від того самого користувача змінює голос, а не створює дубль. Голос можна зняти через DELETE.
Користувач не може голосувати за власний відгук.
Видалення категорії із локаціями заборонене (on_delete=PROTECT).
Інтегрітет даних гарантується не лише серіалізаторами, а й обмеженнями БД: UniqueConstraint для відгуків, голосів і підписок, CheckConstraint для рейтингу.
Відомі обмеження
Листи надсилаються синхронно в процесі веб-сервера. У продакшені їх варто винести у фонову чергу (наприклад, Celery).
У docker-compose.yml використовується runserver: це конфігурація для розробки. Для продакшену потрібні WSGI-сервер і зворотний проксі.
Анонімні перегляди ідентифікуються за IP із заголовка X-Forwarded-For, який без довіреного проксі можна підробити.
Таблиця LocationView необмежено росте. Для великого навантаження потрібне періодичне агрегування або очищення старих записів.
views_7d і popularity у закешованому списку можуть відставати до 5 хвилин. Деталі локації не кешуються й завжди актуальні.
Масові операції через QuerySet.update() не викликають сигналів і не скидають кеш.
Обмеження частоти запитів налаштоване лише для публічних auth-ендпоінтів.