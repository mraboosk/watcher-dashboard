# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import logging

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
import horizon.tables
from horizon.utils import filters

LOG = logging.getLogger(__name__)

MIGRATION_STATUS_DISPLAY_CHOICES = (
    ("queued", pgettext_lazy("Status of a migration", u"Queued")),
    ("preparing", pgettext_lazy("Status of a migration", u"Preparing")),
    ("pre-migrating", pgettext_lazy("Status of a migration", u"Pre-Migrating")),
    ("running", pgettext_lazy("Status of a migration", u"Running")),
    ("post-migrating", pgettext_lazy("Status of a migration", u"Post-Migrating")),
    ("migrating", pgettext_lazy("Status of a migration", u"Migrating")),
    ("confirming", pgettext_lazy("Status of a migration", u"Confirming")),
    ("reverting", pgettext_lazy("Status of a migration", u"Reverting")),
    ("finished", pgettext_lazy("Status of a migration", u"Finished")),
    ("completed", pgettext_lazy("Status of a migration", u"Completed")),
    ("reverted", pgettext_lazy("Status of a migration", u"Reverted")),
    ("done", pgettext_lazy("Status of a migration", u"Done")),
    ("error", pgettext_lazy("Status of a migration", u"Error")),
    ("failed", pgettext_lazy("Status of a migration", u"Failed")),
    ("cancelled", pgettext_lazy("Status of a migration", u"Cancelled")),
)

RUNNING_STATES = frozenset({
    'queued', 'preparing', 'pre-migrating', 'running',
    'post-migrating', 'migrating', 'confirming', 'reverting', 'finished',
})
HISTORY_STATES = frozenset({
    'completed', 'reverted', 'done', 'error', 'failed', 'cancelled',
})


class RunningMigrationsTable(horizon.tables.DataTable):
    id = horizon.tables.Column(
        'id',
        verbose_name=_("ID"),
        link="horizon:admin:migrations:detail")
    migration_uuid = horizon.tables.Column(
        'uuid',
        verbose_name=_("Migration UUID"))
    instance_uuid = horizon.tables.Column(
        'instance_uuid',
        verbose_name=_("Instance UUID"))
    source_compute = horizon.tables.Column(
        'source_compute',
        verbose_name=_("Source Host"))
    dest_compute = horizon.tables.Column(
        'dest_compute',
        verbose_name=_("Destination Host"))
    migration_type = horizon.tables.Column(
        'migration_type',
        verbose_name=_("Type"))
    status = horizon.tables.Column(
        'status',
        verbose_name=_("Status"),
        status=True,
        status_choices=MIGRATION_STATUS_DISPLAY_CHOICES)
    created_at = horizon.tables.Column(
        'created_at',
        filters=(filters.parse_isotime,),
        verbose_name=_("Started At"))

    def get_object_id(self, datum):
        return datum.id

    class Meta(object):
        name = "running_migrations"
        verbose_name = _("Running Migrations")
        hidden_title = False


class MigrationHistoryTable(horizon.tables.DataTable):
    id = horizon.tables.Column(
        'id',
        verbose_name=_("ID"),
        link="horizon:admin:migrations:detail")
    migration_uuid = horizon.tables.Column(
        'uuid',
        verbose_name=_("Migration UUID"))
    instance_uuid = horizon.tables.Column(
        'instance_uuid',
        verbose_name=_("Instance UUID"))
    source_compute = horizon.tables.Column(
        'source_compute',
        verbose_name=_("Source Host"))
    dest_compute = horizon.tables.Column(
        'dest_compute',
        verbose_name=_("Destination Host"))
    migration_type = horizon.tables.Column(
        'migration_type',
        verbose_name=_("Type"))
    status = horizon.tables.Column(
        'status',
        verbose_name=_("Status"),
        status=True,
        status_choices=MIGRATION_STATUS_DISPLAY_CHOICES)
    updated_at = horizon.tables.Column(
        'updated_at',
        filters=(filters.parse_isotime,),
        verbose_name=_("Completed At"))

    def get_object_id(self, datum):
        return datum.id

    class Meta(object):
        name = "migration_history"
        verbose_name = _("Migration History")
        hidden_title = False
