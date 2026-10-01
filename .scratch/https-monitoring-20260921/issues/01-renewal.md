# Проверить продление после обновления VPS/Nginx

Status: done

## Comments

- 21 сентября пользователь прислал active/enabled для certbot.timer, следующий
  запуск 20:01:29 MSK. Вывода Certbot не было; отдельно запрошен только этот результат.

- Пользователю передан блок nginx -t, certbot renew --cert-name dari-sinergii.ru
  --dry-run --run-deploy-hooks --non-interactive и сведения о certbot.timer.
- Ожидается фактический вывод. Публичный сертификат проверен, но сам по себе
  не доказывает работоспособность автоматического продления.
- В историческом handoff от 15 сентября отмечен успешный тест webroot и reload-hook.
  Новый тест относится к состоянию после последующих обновлений конфигурации.

- 21 сентября получен вывод: all simulated renewals succeeded, сертификат для
  основного домена и двух дополнительных имён success. Deploy-hook запущен;
  Nginx syntax/test successful. Упоминание error output относится к stderr nginx -t.
  Таймер active/enabled подтверждён отдельно. Повторная проверка завершена.
