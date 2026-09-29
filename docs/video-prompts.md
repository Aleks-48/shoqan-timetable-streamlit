# Shoqan Day: сценарий и промпты для видео

Подготовлены два варианта: демонстрация проекта и отдельный творческий ролик для AI VIDEO. Готовое видео не сгенерировано. Названия ИИ-инструментов в заявке нужно заполнить после фактического использования.

## Формат

Рекомендуемый мастер: 1920×1080, 16:9, 24 или 25 кадров/с, около 45 секунд. Это выбор автора, не подтверждённое требование конкурса. Для файла до 20 МБ при 45 сек ориентир общего битрейта — не более 3,3 Мбит/с, с запасом: видео H.264 2,6 Мбит/с и AAC 128 кбит/с. После экспорта проверить реальный размер и воспроизведение. Подаётся видеофайл MP4, а не только ссылка.

## Сценарий 45 секунд

| Время | Изображение | Текст/озвучка |
|---|---|---|
| 0–6 | ИИ-сцена студента, который сверяет несколько листов | «Где следующая пара? В какой аудитории? Расписание должно давать ответ сразу.» |
| 6–18 | Настоящая запись MVP: выбор группы, ближайшая пара, неделя | «Shoqan Day собирает учебный день в одном месте. Выбираешь группу, видишь занятия и находишь нужный предмет.» |
| 18–27 | Настоящая запись: темы, CSV с ошибкой, экспорт ICS | «Три темы, проверка файла перед импортом и перенос недели в календарь уже работают.» |
| 27–38 | Условная визуализация сканирования документа, затем макет сверки | «Следующий этап — ИИ-распознавание расписания. Модель извлекает строки, человек сверяет их с источником и подтверждает.» |
| 38–45 | Настоящий экран приложения, финальное название | «Сейчас это MVP на демонстрационных данных. Следующий шаг — пилот с одной группой и согласованным источником.» |

На фрагменте 27–38 секунд постоянно показывать подпись «Концепция следующей версии. ИИ-импорт ещё не подключён». На экранах демо не скрывать предупреждение о вымышленных данных. Точный русский текст и интерфейс добавлять в видеоредакторе, не поручать модели генерировать читаемые надписи.

## Общая инструкция для генерации сцен

Кинематографичный, но реалистичный студенческий ролик. Спокойная палитра: глубокий синий, молочный белый, мягкий дневной свет. Одна и та же взрослая вымышленная героиня 20–22 лет, тёмно-синий свитер, тёмные волосы до плеч. Современное учебное пространство без логотипов и вывесок. Это художественная иллюстрация, не съёмка реального кампуса. Никаких вымышленных достижений, статистики или читаемых надписей.

### Сцена A: проблема, 6 секунд

```text
6-second cinematic realistic video, 16:9. A fictional adult university student, age 21, shoulder-length dark hair, navy sweater, sitting at a simple desk in a contemporary study room. She compares two printed timetable sheets, then briefly glances at a phone lying flat on the desk. The printed sheets have indistinct rows with no readable text. Quiet, mildly puzzled expression, no exaggerated stress. Gentle slow camera push-in from a medium shot. Soft morning light from the left, navy and warm white palette. Keep the right third visually clean for an editorial caption. Natural hands and anatomy. No logos, no readable text, no subtitles, no watermark, no recognizable university building.
```

### Сцена B: концепция распознавания, 5 секунд

```text
5-second restrained editorial technology video, 16:9. Overhead shot of one paper timetable on a clean pale desk. A smartphone camera hovers steadily above it, held by the same fictional adult student in a navy sweater. A soft translucent scanning highlight moves once across the paper. The paper contains abstract lines only, no readable text. Realistic paper texture, natural hand movement, soft daylight, minimal visual effects. Leave the lower quarter clean for the editor to add the label "Concept of a future version". No holograms, no floating dashboards, no logos, no invented UI, no watermark.
```

### Сцена C: результат, 5 секунд

```text
5-second cinematic realistic video, 16:9. The same fictional adult university student in a navy sweater closes her notebook and calmly walks toward a classroom entrance in a generic modern education building. Soft daylight, subtle camera follow, natural pace and expression. Navy and cream color palette consistent with the previous scenes. No readable room number or institutional signage. No logos, no text, no subtitles, no watermark, no dramatic celebration. This is a fictional illustrative scene, not a representation of a real university campus.
```

## Запись интерфейса

Записать реальное приложение отдельными дублями: «Мой день», «Неделя», переключение тем, поиск «Базы данных», импорт некорректного CSV с сообщением об ошибке, скачивание ICS. Курсор двигать медленно. На демонстрацию каждой функции оставить 2–4 секунды. Не показывать электронную почту, вкладки личных аккаунтов и файлы с персональными данными.

Промпт для монтажного ассистента:

```text
Собери ролик Shoqan Day длительностью около 45 секунд из приложенных настоящих записей приложения и отдельно помеченных художественных ИИ-сцен. Используй последовательность из сценария. Не подменяй интерфейс сгенерированным. Сохрани предупреждение «Демо» на реальных экранах. На концепции распознавания постоянно укажи, что функция ещё не подключена. Добавь русский голос по готовому тексту, спокойную ненавязчивую музыку с разрешённой лицензией, субтитры максимум в две строки. Финал: название Shoqan Day и «Пилот одной группы — следующий шаг». Не добавляй имена, контакты, логотип университета, вымышленные цифры или заявления об официальном внедрении. Экспорт H.264 MP4, 1080p, до 20 МБ.
```

## Описание для отдельной видеозаявки

**Название:** Shoqan Day: понятный учебный день

**Черновик описания:** Ролик показывает идею удобного расписания и рабочий студенческий MVP. Художественные сцены созданы с помощью [фактически использованный инструмент]. Озвучка создана [инструмент или собственный голос], монтаж выполнен в [редактор]. Интерфейс показан настоящей записью приложения. Распознавание расписания с помощью ИИ представлено как концепция будущей версии и обозначено в кадре. Иллюстративные сцены не изображают реальный кампус.

Квадратные скобки необходимо заменить после создания видео. Не отправлять этот черновик без замены. Для проектной заявки ролик не подтверждён как обязательный, презентация подаётся отдельным файлом.
