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
import horizon.exceptions
import horizon.tables
import horizon.views
from horizon.utils import memoized
from openstack_dashboard.api import _nova

from watcher_dashboard.content.migrations import tables

LOG = logging.getLogger(__name__)


class IndexView(horizon.tables.MultiTableView):
    table_classes = (
        tables.RunningMigrationsTable,
        tables.MigrationHistoryTable,
    )
    template_name = 'infra_optim/migrations/index.html'
    page_title = _("Migrations")

    @memoized.memoized_method
    def _get_migrations(self):
        try:
            return _nova.novaclient(self.request).migrations.list()
        except Exception:
            horizon.exceptions.handle(
                self.request,
                _("Unable to retrieve migration information."))
            return []

    def get_running_migrations_data(self):
        return [m for m in self._get_migrations()
                if m.status in tables.RUNNING_STATES]

    def get_migration_history_data(self):
        return [m for m in self._get_migrations()
                if m.status in tables.HISTORY_STATES]


class DetailView(horizon.views.HorizonTemplateView):
    template_name = 'infra_optim/migrations/details.html'
    redirect_url = 'horizon:admin:migrations:index'
    page_title = _("Migration Details: {{ migration.id }}")

    @memoized.memoized_method
    def _get_data(self):
        migration_id = None
        try:
            migration_id = self.kwargs['migration_id']
            return _nova.novaclient(self.request).migrations.get(migration_id)
        except Exception:
            msg = _('Unable to retrieve details for migration "%s".') \
                % migration_id
            horizon.exceptions.handle(
                self.request, msg,
                redirect=self.redirect_url)

    def get_context_data(self, **kwargs):
        context = super(DetailView, self).get_context_data(**kwargs)
        context['migration'] = self._get_data()
        return context
