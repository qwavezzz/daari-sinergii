from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ManagerMigrationTests(TransactionTestCase):
    def test_preserves_effective_recipient_and_can_roll_back(self):
        before = ("orders", "0008_packingrecipe_test_only")
        after = ("orders", "0009_remove_storesettings_manager_email_and_more")
        try:
            for canonical in ("", "canonical@example.test"):
                executor = MigrationExecutor(connection)
                executor.migrate([before])
                old = executor.loader.project_state([before]).apps
                old.get_model("orders", "StoreSettings").objects.update_or_create(
                    pk=1, defaults={"manager_email": "legacy@example.test"}
                )
                old.get_model("orders", "NotificationSettings").objects.update_or_create(
                    pk=1, defaults={"manager_email": canonical}
                )
                executor = MigrationExecutor(connection)
                executor.migrate([after])
                current = executor.loader.project_state([after]).apps
                self.assertEqual(
                    current.get_model("orders", "NotificationSettings").objects.get(pk=1).manager_email,
                    canonical or "legacy@example.test",
                )
                executor = MigrationExecutor(connection)
                executor.migrate([before])
                old = executor.loader.project_state([before]).apps
                self.assertEqual(
                    old.get_model("orders", "StoreSettings").objects.get(pk=1).manager_email,
                    canonical or "legacy@example.test",
                )
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
