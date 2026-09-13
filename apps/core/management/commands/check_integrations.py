from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand, CommandError

from apps.orders.models import StoreSettings
from apps.orders.notifications import smtp_configuration_error
from apps.payments.provider import PaymentError, YooKassaClient


class Command(BaseCommand):
    help = "Проверить тестовую ЮKassa и SMTP. Письмо отправляется только с --send-test-email."

    def add_arguments(self, parser):
        parser.add_argument("--send-test-email", action="store_true")
        parser.add_argument("--only", choices=["payments", "email"])

    def handle(self, *args, **options):
        failures = []
        if options["only"] != "email":
            if not settings.YOOKASSA_TEST_MODE:
                failures.append("ЮKassa: проверка разрешена только в тестовом режиме.")
            else:
                try:
                    YooKassaClient().verify_shop()
                except PaymentError as exc:
                    failures.append("ЮKassa: " + str(exc))
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "ЮKassa: доступ к тестовому магазину подтверждён. Платёж не создавался."
                        )
                    )
        if options["only"] != "payments":
            error = smtp_configuration_error()
            store = StoreSettings.objects.filter(pk=1).first()
            recipient = (store.manager_email if store else "") or settings.MANAGER_EMAIL
            if options["send_test_email"] and not recipient:
                error = "Укажите почту менеджера в настройках магазина."
            if error:
                failures.append("Почта: " + error)
            else:
                try:
                    with get_connection() as connection:
                        if options["send_test_email"]:
                            email = EmailMessage(
                                "[ТЕСТ] Проверка уведомлений — Дары Синергии",
                                "Это проверочное письмо сайта «Дары Синергии». Заказ не создавался, оплаты нет.\n"
                                "Уведомления менеджеру будут поступать на этот адрес.\n"
                                + settings.SHOP_ORIGIN
                                + "/admin/",
                                settings.DEFAULT_FROM_EMAIL,
                                [recipient],
                                connection=connection,
                            )
                            if email.send() != 1:
                                raise RuntimeError
                except Exception as exc:
                    failures.append(
                        f"Почта: соединение или отправка не удались ({type(exc).__name__}). Проверьте настройки SMTP."
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Почта: проверочное письмо принято сервером. Проверьте входящие и спам."
                            if options["send_test_email"]
                            else "Почта: соединение и авторизация SMTP успешны. Письмо не отправлялось."
                        )
                    )
        if failures:
            raise CommandError("\n".join(failures))
