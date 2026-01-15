# Мониторинг Kafka и баз данных

Система мониторинга настроена с использованием Prometheus и Grafana.

## Быстрый старт

1. Запустите все сервисы:
```bash
docker-compose up -d
```

2. Откройте Grafana:
   - URL: http://localhost:3000
   - Логин: `admin`
   - Пароль: `admin`

3. Откройте Prometheus:
   - URL: http://localhost:9090

## Доступные дашборды

После запуска в Grafana будут доступны следующие дашборды:

1. **Kafka Overview** - мониторинг Kafka топиков
   - Сообщения в/из топиков
   - Consumer lag
   - Партиции
   - Пропускная способность

2. **PostgreSQL Overview** - мониторинг базы данных
   - Размер БД
   - Активные соединения
   - Транзакции в секунду
   - Операции с данными
   - Cache hit ratio

3. **Redis Overview** - мониторинг кеша
   - Подключенные клиенты
   - Использование памяти
   - Команды в секунду
   - Hit rate

4. **Application Overview** - метрики приложения
   - Обработка документов
   - События Kafka
   - Генерация embeddings
   - Время обработки

## Экспортеры метрик

- **Kafka Exporter**: http://localhost:9308/metrics
- **PostgreSQL Exporter**: http://localhost:9187/metrics
- **Redis Exporter**: http://localhost:9121/metrics
- **Application Metrics**: http://localhost:8000/metrics

## Кастомные метрики приложения

Приложение экспортирует следующие метрики:

- `documents_discovered_total` - обнаружено документов
- `documents_fetched_total{status}` - скачано документов
- `documents_parsed_total{status}` - распарсено документов
- `document_processing_duration_seconds{stage}` - время обработки
- `kafka_events_published_total{topic,status}` - опубликовано событий
- `kafka_events_failed_total{topic,error_type}` - ошибок публикации
- `embeddings_generated_total` - сгенерировано embeddings
- `embedding_generation_duration_seconds` - время генерации embeddings

## Проверка работы

1. Проверьте, что все контейнеры запущены:
```bash
docker ps | grep -E "prometheus|grafana|exporter"
```

2. Проверьте targets в Prometheus:
   - Откройте http://localhost:9090/targets
   - Все targets должны быть в состоянии "UP"

3. Проверьте метрики:
```bash
curl http://localhost:8000/metrics
```

## Настройка алертов (опционально)

Для настройки алертов:
1. Создайте файл `monitoring/alert_rules.yml`
2. Добавьте правила в `prometheus.yml`:
```yaml
rule_files:
  - "alert_rules.yml"
```
3. Настройте Alertmanager (опционально)

## Хранение данных

- **Prometheus**: 30 дней (настраивается в `prometheus.yml`)
- **Grafana**: Постоянное хранение в volume `grafana_data`

## Полезные ссылки

- Prometheus UI: http://localhost:9090
- Grafana: http://localhost:3000
- PromQL документация: https://prometheus.io/docs/prometheus/latest/querying/basics/
