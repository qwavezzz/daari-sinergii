"""Reconcile the overlapping notification migrations from the two branches."""

from django.db import migrations
from django.utils import timezone


class AddFieldIfMissing(migrations.AddField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        with schema_editor.connection.cursor() as cursor:
            columns = schema_editor.connection.introspection.get_table_description(
                cursor, model._meta.db_table
            )
        if model._meta.get_field(self.name).column not in {column.name for column in columns}:
            super().database_forwards(app_label, schema_editor, from_state, to_state)


class RemoveConstraintIfExists(migrations.RemoveConstraint):
    def state_forwards(self, app_label, state):
        model = state.models[app_label, self.model_name_lower]
        if any(item.name == self.name for item in model.options.get("constraints", [])):
            super().state_forwards(app_label, state)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        if not any(item.name == self.name for item in model._meta.constraints):
            return
        with schema_editor.connection.cursor() as cursor:
            constraints = schema_editor.connection.introspection.get_constraints(cursor, model._meta.db_table)
        if self.name in constraints:
            super().database_forwards(app_label, schema_editor, from_state, to_state)


def skip_duplicate_notifications(apps, schema_editor):
    notices = apps.get_model("orders", "Notification").objects.using(schema_editor.connection.alias)
    seen = set()
    for notice in notices.filter(skipped_at__isnull=True).order_by("audience", "pk").iterator():
        key = (notice.order_id, notice.event, notice.recipient)
        if key in seen:
            notices.filter(pk=notice.pk).update(skipped_at=timezone.now())
        seen.add(key)
