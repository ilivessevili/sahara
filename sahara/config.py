# Copyright (c) 2013 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import itertools

from oslo.config import cfg

from sahara import exceptions as ex
from sahara.i18n import _
from sahara.openstack.common import lockutils
from sahara.openstack.common import log
from sahara.openstack.common import periodic_task
from sahara.openstack.common import policy
from sahara.plugins import base as plugins_base
from sahara.topology import topology_helper
from sahara.utils.notification import sender
from sahara.utils.openstack import cinder
from sahara.utils.openstack import keystone
from sahara.utils import remote
from sahara import version


cli_opts = [
    cfg.StrOpt('host', default='',
               help='Hostname or IP address that will be used to listen on.'),
    cfg.IntOpt('port', default=8386,
               help='Port that will be used to listen on.'),
    cfg.BoolOpt('log-exchange', default=False,
                help='Log request/response exchange details: environ, '
                     'headers and bodies.')
]

edp_opts = [
    cfg.IntOpt('job_binary_max_KB',
               default=5120,
               help='Maximum length of job binary data in kilobytes that '
                    'may be stored or retrieved in a single operation.'),
    cfg.IntOpt('job_canceling_timeout',
               default=300,
               help='Timeout for canceling job execution (in seconds). '
                    'Sahara will try to cancel job execution during '
                    'this time.')
]

db_opts = [
    cfg.StrOpt('db_driver',
               default='sahara.db',
               help='Driver to use for database access.')
]

networking_opts = [
    cfg.BoolOpt('use_floating_ips',
                default=True,
                help='If set to True, Sahara will use floating IPs to '
                     'communicate with instances. To make sure that all '
                     'instances have floating IPs assigned in Nova Network '
                     'set "auto_assign_floating_ip=True" in nova.conf. '
                     'If Neutron is used for networking, make sure that '
                     'all Node Groups have "floating_ip_pool" parameter '
                     'defined.'),
    cfg.StrOpt('node_domain',
               default='novalocal',
               help="The suffix of the node's FQDN. In nova-network that is "
                    "the dhcp_domain config parameter."),
    cfg.BoolOpt('use_neutron',
                default=False,
                help="Use Neutron Networking (False indicates the use of Nova "
                     "networking)."),
    cfg.BoolOpt('use_namespaces',
                default=False,
                help="Use network namespaces for communication (only valid to "
                     "use in conjunction with use_neutron=True)."),
    cfg.BoolOpt('use_rootwrap',
                default=False,
                help="Use rootwrap facility to allow non-root users to run "
                     "the sahara-all server instance and access private "
                     "network IPs (only valid to use in conjunction with "
                     "use_namespaces=True)"),
    cfg.StrOpt('rootwrap_command',
               default='sudo sahara-rootwrap /etc/sahara/rootwrap.conf',
               help="Rootwrap command to leverage.  Use in conjunction with "
                    "use_rootwrap=True")
]


cfg.set_defaults(log.log_opts, default_log_levels=[
    'amqplib=WARN',
    'qpid.messaging=INFO',
    'stevedore=INFO',
    'eventlet.wsgi.server=WARN',
    'sqlalchemy=WARN',
    'boto=WARN',
    'suds=INFO',
    'keystone=INFO',
    'paramiko=WARN',
    'requests=WARN',
    'iso8601=WARN',
])


CONF = cfg.CONF
CONF.register_cli_opts(cli_opts)
CONF.register_opts(networking_opts)
CONF.register_opts(edp_opts)
CONF.register_opts(db_opts)


def list_opts():
    return [
        ('DEFAULT',
         itertools.chain(cli_opts,
                         edp_opts,
                         networking_opts,
                         db_opts,
                         lockutils.util_opts,
                         policy.policy_opts,
                         log.common_cli_opts,
                         log.generic_log_opts,
                         log.log_opts,
                         log.logging_cli_opts,
                         periodic_task.periodic_opts,
                         plugins_base.opts,
                         topology_helper.opts,
                         sender.notifier_opts,
                         cinder.opts,
                         keystone.opts,
                         remote.ssh_opts,
                         )),
    ]


def main_opts():
    # NOTE (vgridnev): we make these import here to avoid problems
    #                  with importing unregistered options in sahara code.
    #                  As example, importing 'node_domain' in
    #                  sahara/conductor/objects.py

    from sahara.conductor import api
    from sahara import main as sahara_main
    from sahara.service.edp import job_utils
    from sahara.service import periodic
    from sahara.service import volumes
    from sahara.utils import proxy

    return [
        ('DEFAULT',
         itertools.chain(sahara_main.opts,
                         job_utils.opts,
                         periodic.periodic_opts,
                         volumes.opts,
                         proxy.opts)),
        ('conductor',
         itertools.chain(api.conductor_opts)),
    ]


def parse_configs(conf_files=None):
    try:
        version_string = version.version_info.version_string()
        CONF(project='sahara', version=version_string,
             default_config_files=conf_files)
    except cfg.RequiredOptError as roe:
        raise ex.ConfigurationError(
            _("Option '%(option)s' is required for config group '%(group)s'") %
            {'option': roe.opt_name, 'group': roe.group.name})
    validate_configs()


def validate_network_configs():
    if CONF.use_namespaces and not CONF.use_neutron:
        raise ex.ConfigurationError(
            _('use_namespaces can not be set to "True" when use_neutron '
              'is set to "False"'))


def validate_configs():
    validate_network_configs()
