#!/usr/bin/env python
#
# (c) 2015, Joseph Callen <jcallen () csc.com>
# Portions Copyright (c) 2015 VMware, Inc. All rights reserved.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.


DOCUMENTATION = '''
module: vio_ldap
short_description: Validate active directory bind, admin, test project users for chaperone VIO.
description:
    - This module is indented to be used to validate the specified admin, bind and project users for
      the configuration of VIO if Active Directory is the authentication source. This module will
      attempt to bind with the bind and admin user, then search for the admin user and bind user
      within the specified user dn tree and optional filter. Will search for a group in the group
      dn tree and optional filter.
author: Jake Dupuy jdupuy@vmware.com
credits: VIO Team for all the continued support
options:
    domain_controller:
        description:
            - keystone authentication url
        required: True
        type: str
    encryption:
        description:
            - The type of encription that will be used. Currently only NONE and SSL supported.
        required: True
        choices: None, SSL
        type: str
    admin_user:
        description:
            - specify the admin user to be validated
        required: True
        type: str
    admin_user_password:
        description:
            - password for the admin user
        required: True
        type: str
    bind_user:
        description:
            - specify the bind user to be validated
        required: True
        type: str
    bind_user_password:
        description:
            - password for the bind user
        required: True
        type: str
    project_user:
        description:
            - specify the project user
        required: True
        type: str
    project_user_password:
        description:
            - password for the project user
        required: True
        type: str
    user_dn_tree:
        description:
            - user tree DN ex: ou=vio,dc=corp,dc=local
        required: True
        type: str
    user_filter:
        description:
            - valid ldap query to use for searching for the specified users ex: (&(objectCategory=person)(objectClass=user))
        required: True
        type: str
    group_dn_tree:
        description:
            - group tree DN ex: ou=vio,dc=corp,dc=local
        required: True
        type: str
    group_filter:
        description:
            - valid ldap query to use for searching for a group in specified dn ex: (&(objectClass=group)(objectCategory=group))
        required: True
        type: str

requirements: python-ldap, python-ldapurl
'''

EXAMPLE = '''
- name: Validate AD users for Openstack Deployment when AD as authentication source
  vio_ldap:
    domain_controller: "{{ vio_authentication_ad_dc_hostname }}"
    encryption: "{{ vio_authentication_ad_encryption }}"
    admin_user: "{{ vio_authentication_ad_admin_user }}"
    admin_user_password: "{{ vio_authentication_ad_admin_user_password }}"
    bind_user: "{{ vio_authentication_ad_bind_user }}"
    bind_user_password: "{{ vio_authentication_ad_bind_user_password }}"
    project_user: "{{ vio_val_user_name_ad }}"
    project_user_password: "{{ vio_val_user_pass_ad }}"
    user_dn_tree: "{{ vio_authentication_ad_ldap_user_tree_dn }}"
    user_filter: "{{ vio_authentication_ad_ldap_user_filter }}"
    group_dn_tree: "{{ vio_authentication_ad_ldap_group_tree_dn }}"
    group_filter: "{{ vio_authentication_ad_ldap_group_filter }}"

'''


try:
    import sys
    import ldap
    import ldapurl
    IMPORTS = True
except ImportError:
    IMPORTS = False

def _setup_url(prefix, ldap_port, dc_hostname):
    ldap_url = "{}://{}:{}".format(prefix, dc_hostname, ldap_port)
    return ldap_url


def ldap_setup_url(module, hostname, encryption=None):

    prefix = 'ldap'
    port = 389

    if encryption == 'SSL':
        prefix = 'ldaps'
        port = 636

    server = _setup_url(prefix, port, hostname)

    if ldapurl.isLDAPUrl(server):
        return server
    else:
        fail_msg = "Invalid ldap uri for: {}".format(server)
        module.fail_json(msg=fail_msg)


def ldap_initialize(module, server):

    ldapmodule_trace_level = 1
    ldapmodule_trace_file = sys.stderr
    ldap._trace_level = ldapmodule_trace_level

    try:
        conn = ldap.initialize(
            server,
            trace_level=ldapmodule_trace_level,
            trace_file=ldapmodule_trace_file
        )

    except ldap.LDAPError as e:
        fail_msg = "LDAP Error initializing: {}".format(ldap_errors(e))
        module.fail_json(msg=fail_msg)

    return conn


def ldap_bind_with_user(module, conn, username, password):

    result = False

    try:

        conn.simple_bind_s(username, password)
        result = True

    except ldap.INVALID_CREDENTIALS:
        fail_msg = "Invalid Credentials for user {}".format(username)
        module.fail_json(msg=fail_msg)
    except ldap.LDAPError as e:
        fail_msg = "LDAP Error Binding user: {}: ERROR: {}".format(username, ldap_errors(e))
        module.fail_json(msg=fail_msg)

    return result


def ldap_search(module, conn, dn, search_filter, ldap_attrs):

    try:
        search = conn.search_s(dn, ldap.SCOPE_SUBTREE, search_filter, ldap_attrs)
    except ldap.LDAPError as e:
        fail_msg = "LDAP Error Searching: {}".format(ldap_errors(e))
        module.fail_json(msg=fail_msg)

    return search


def ldap_errors(error):
    if type(error.message) == dict and error.message.has_key('info'):
        return error.message['info']
    else:
        return error.message


def ldap_search_results(results, ldap_attr, target):
    results_list = [j for i in results for j in i if type(j) == dict]

    attr_results = [v for x in results_list for k, v in x.items() if k == ldap_attr]

    target_list = [x for r in attr_results for x in r]

    if target in target_list:
        return target
    else:
        return False


def ldap_unbind(module, conn):
    result = False

    try:
        conn.unbind_s()
        result = True
    except ldap.LDAPError as e:
        fail_msg = "LDAP Error unbinding: {}".format(e)
        module.fail_json(msg=fail_msg)

    return result


def set_filter_for_search(search_type, search_filter=None):

    if search_type == 'user' and search_filter:
        return search_filter
    elif search_type == 'user' and search_filter is None:
        return '(&(objectCategory=person)(objectClass=user))'
    elif search_type == 'group' and search_filter:
        return search_filter
    elif search_type == 'group' and search_filter is None:
        return '(&(objectClass=group)(objectCategory=group))'



def main():
    argument_spec = dict(
        domain_controller=dict(type='str', required=True),
        encryption=dict(type='str', required=True),
        admin_user=dict(type='str', required=True),
        admin_user_password=dict(type='str', required=True),
        bind_user=dict(type='str', required=True),
        bind_user_password=dict(type='str', required=True),
        project_user=dict(type='str', required=True),
        project_user_password=dict(type='str', required=True),
        user_dn_tree=dict(type='str', required=True),
        user_filter=dict(type='str', required=False),
        group_dn_tree=dict(type='str', required=True),
        group_filter=dict(type='str', required=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not IMPORTS:
        module.fail_json(msg="failed to import required modules")

    failed = True
    msg = "Failed to validate AD users"

    domain_controller = module.params['domain_controller']
    encryption = module.params['encryption']
    admin_user = module.params['admin_user']
    admin_password = module.params['admin_user_password']
    bind_user = module.params['bind_user']
    bind_password = module.params['bind_user_password']
    project_user = module.params['project_user']
    project_password = module.params['project_user_password']
    user_dn_tree = module.params['user_dn_tree']
    user_filter = module.params['user_filter']
    group_dn_tree = module.params['group_dn_tree']
    group_filter = module.params['group_filter']

    server = ldap_setup_url(module, domain_controller, encryption)
    conn = ldap_initialize(module, server)

    conn.protocol_version=ldap.VERSION3
    conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
    conn.set_option(ldap.OPT_REFERRALS, ldap.OPT_OFF)

    test_bind_user = ldap_bind_with_user(module, conn, bind_user, bind_password)

    if not test_bind_user:
        module.fail_json(msg="Failed to bind with bind user")

    test_admin_user = ldap_bind_with_user(module, conn, admin_user, admin_password)

    if not test_admin_user:
        module.fail_json(msg="Failed to bind with admin user")

    test_project_user = ldap_bind_with_user(module, conn, project_user, project_password)

    if not test_project_user:
        module.fail_json(msg="Failed to bind with Project user")

    admin_search = ldap_search(module, conn, user_dn_tree, user_filter, ['userPrincipalName'])

    if not admin_search:
        module.fail_json(msg="Failed to bind with admin or bind user")

    admin_search_results = ldap_search_results(admin_search, 'userPrincipalName', admin_user)

    if not admin_search_results:
        fail_msg = "Failed to find admin user: {}".format(admin_user)
        module.fail_json(msg=fail_msg)

    bind_search = ldap_search(module, conn, user_dn_tree, user_filter, ['userPrincipalName'])

    if not bind_search:
        fail_msg = "Failed to find bind user: {}".format(bind_user)
        module.fail_json(msg=fail_msg)

    bind_search_results = ldap_search_results(bind_search, 'userPrincipalName', bind_user)

    if not bind_search_results:
        fail_msg = "Failed to find bind user: {} in tree dn: {}".format(bind_user, user_dn_tree)
        module.fail_json(msg=fail_msg)

    group_search = ldap_search(module, conn, group_dn_tree, group_filter, ['cn'])

    if not group_search:
        fail_msg = "Failed to find a group in greo dn tree: {} and filter: {}".format(group_dn_tree, group_filter)
        module.fail_json(msg=fail_msg)

    failed = False
    msg = "Validated AD Users"

    ldap_unbind(module, conn)

    module.exit_json(changed=False, failed=failed, msg=msg)

from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
