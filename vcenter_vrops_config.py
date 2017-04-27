#!/usr/bin/python
# coding=utf-8
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

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
module: vcenter_vrops_config
Short_description: Configuration for vROPs Module is currently WIP!!!!
description:
    Configuration for vROPs. Consumes internal vrops casa api.
requirements:
    - ansible 2.x
    - requests
Tested on:
    - vcenter 6.0
    - esx 6
    - ansible 2.1.2
    - vRealize-Operations-Manager-Appliance-6.4.0.4635874
author: VMware
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    username:
        description:
            - The username of the vSphere vCenter with Admin rights
        required: True
        aliases: ['user', 'admin']
    password:
        description:
            - The password of the vSphere vCenter user
        required: True
        aliases: ['pass', 'pwd']
    state:
        description:
            - Desired state of the disk group
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: vROPs Configure
  vcenter_vrops_config:
    administrator: 'admin'
    password: 'pass123!'
    vrops_ip_addess: '128.123.123.3'
    state: 'present'
  tags:
    - vrops_config
'''

RETURN = '''
description: Module currently in WIP
returned: 
type: 
sample: 
'''

try:
    import time
    import requests
    IMPORTS = True
except ImportError:
    IMPORTS = False


## vrops api paths this needs fixings
_security         = 'security/%s'
_deployment       = 'deployment/%s'
_sysadmin         = 'sysadmin/%s'
_cluster          = 'cluster/%s'
cluster           = 'cluster'
_node             = 'node/%s'
node              = 'node'
_slice            = 'slice/%s'
slice_            = 'slice'
_role             = 'role/%s'
role              = 'role'
_info             = 'info'

ntp               = 'ntp'
_ntp              = '%s/%s'
_status           = 'status'
_ntp_status       = _ntp % (ntp, _status)

adminpassword     = 'adminpassword'
admin_pass_init   = 'initial'
admin_pass        = '%s/%s'

_headers          = { 'Content-Type': 'application/json', 'Accept': 'application/json' }

# need a better way to read in body for different calls this is static
_set_admin_role_body = [{ "slice_address": "", "admin_slice": "",
                          "is_ha_enabled": True, "user_id": "", "password": "",
                          "slice_roles": ["ADMIN","DATA","UI"] }]

class VropsRestClientExceptions(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        log(self.msg)
        return self.msg


class VropsRestClient(object):
    """ A basic vROPs rest client to configure the appliance
    """
    def __init__(self, username, password, server):
        super(VropsRestClient, self).__init__()
        self._username       = username
        self._password       = password
        self._server         = server
        self._base_url       = 'https://%s' % self._server
        self._base_user_url  = 'https://%s/suite-api/api/%s'
        self._base_admin_url = 'https://%s/casa/%s'
        self.auth            = (self._username, self._password)

    def do_request(self, request_type, status_codes, params):
        """Returns status code of rest call and json content
        returns None, None on failure
        :param request_type: get, put, post, delete
        :param status_codes: list of accepted status codes
        :param params: dict of requests.<request_type> accepted parameters
        """
        resp  = None
        content = None
        status_code = None

        try:
            if request_type == 'get':
                resp = requests.get(**params)
            if request_type == 'put':
                resp = requests.put(**params)
            if request_type == 'post':
                resp = requests.post(**params)
            if request_type == 'delete':
                resp = requests.delete(**params)
            status_code = resp.status_code
        except (requests.exceptions.ConnectionError, requests.RequestException) as conn_error:
            msg = "Failed Request GET Error: %s " % str(conn_error)
            raise VropsRestClientExceptions(msg=msg)
        except Exception as e:
            msg = "General Failure: %s " % str(e)
            raise VropsRestClientExceptions(msg=msg)

        if status_code not in status_codes:
            msg = "Status Code: %s not in status codes: %s " % (status_code, status_codes)
            raise VropsRestClientExceptions(msg=msg)
        if status_code == 401:
            msg = "Status Code: %s UNAUTHORIZED" % status_code
            raise VropsRestClientExceptions(msg=msg)

        try:
            content = resp.json()
        except Exception as e:
            pass

        return status_code, content

    def api_url(self, url_tpye=None, path=None):
        url = self._base_url
        if url_tpye == 'admin' and path:
            url = self._base_admin_url % (self._server, path)
        if url_tpye == 'user' and path:
            url = self._base_user_url % (self._server, path)
        return url

    def api_state(self):
        state  = False
        _url   = self.api_url()
        params = {'url': _url, 'verify': False}

        state, content = self.do_request('get', [200], params)

        return state

    def body_to_json(self, body):
        json_body = None

        try:
            json_body = json.dumps(body)
        except Exception as e:
            return json_body

        return json_body

    def _update_ntp_servers(self, ntp_servers, content):
        """Returns list of desired ntp servers to configure
        :param ntp_servers: list of desired ntp servers
        :param content: content from get sysadmin/cluster/ntp
        """
        update_list         = []
        current_ntp_servers = [n['address'] for n in content['time_servers']]

        if set(ntp_servers) == set(current_ntp_servers):
            return update_list

        common_servers = list(set(ntp_servers) & set(current_ntp_servers))
        update_list    = [s for s in ntp_servers if s not in common_servers]

        return update_list

    def ntp_state(self, ntp_servers):
        """Returns bool, list of ntp servers to update
        :param ntp_servers: list of desired ntp servers
        """
        state    = False
        ntp_list = None
        path     = _sysadmin % _cluster % ntp
        url      = self.api_url('admin', path)

        params = {'url': url, 'auth': self.auth,
                  'headers': _headers, 'verify': False}

        status_code, content = self.do_request('get', [200], params)

        if not content['time_servers']:
            log("Currently no ntp servers set state: %s " % state)
            log("ntp_servers: %s " % ntp_servers)
            return False, ntp_servers

        ntp_list = self._update_ntp_servers(ntp_servers, content)

        if not ntp_list:
            state = True

        return state, ntp_list

    def ntp_body(self, ntp_servers):
        body = {'time_servers': []}
        for ntp in ntp_servers:
            body['time_servers'].append({'address': ntp})
        return body

    def set_ntp(self, ntp_servers):
        state  = False
        path   = _sysadmin % _cluster % ntp
        url    = self.api_url('admin', path)
        body   = self.ntp_body(ntp_servers)
        _body  = self.body_to_json(body)
        params = {'url': url, 'auth': self.auth, 'data': _body,
                  'headers': _headers, 'verify': False}

        state, content = self.do_request('post', [200], params)

        return state

    def configure_ntp(self, ntp_servers):
        ntp_state, ntp_list = self.ntp_state(ntp_servers)

        if ntp_state:
            return ntp_state

        set_ntp_servers = self.set_ntp(ntp_list)
        return set_ntp_servers

    def reset_admin_password(self):
        path   = _security % adminpassword
        _url   = self.api_url('admin', path)
        body   = { "old_password": self._password, "password": self._password }
        _body  = self.body_to_json(body)

        params = {'url': _url, 'verify': False, 'auth': self.auth,
                  'data': _body, 'headers': _headers}

        status_code, content = self.do_request('put', [200, 500], params)

        if status_code == 500:
            raise VropsRestClientExceptions(msg="Failed to reset Admin Password")

        return True

    def set_admin_init_password(self):
        state    = False
        path     = _security % admin_pass % (adminpassword, admin_pass_init)
        _url     = self.api_url('admin', path)
        body     = { "password": self._password }
        _body    = self.body_to_json(body)

        params   = {'url': _url, 'verify': False,
                    'data': _body, 'headers': _headers}

        status_code, content = self.do_request('put', [200, 500], params)

        if status_code == 500:
            state = self.reset_admin_password()

        return state

    def admin_role_state(self):
        state  = False
        path   = _deployment % _slice % _role % _status
        _url   = self._base_admin_url % (self._server, path)

        params = {'url': _url, 'auth': self.auth,
                  'verify': False, 'headers': _headers}

        status_code, content = self.do_request('get', [200], params)

        if status_code:
            state = content['configurationRunning']

        return state

    def admin_role_body(self, _admin_role_body):
        for body in _admin_role_body:
            body.update({'slice_address': self._server})
            body.update({'admin_slice': self._server})
            body.update({'user_id': self._username})
            body.update({'password': self._password})
        return _admin_role_body

    def set_admin_role(self):
        state  = False
        path   = _deployment % _slice % role
        _url   = self.api_url('admin', path)
        body   = self.admin_role_body(_set_admin_role_body)
        _body  = self.body_to_json(body)

        params = {'url': _url, 'verify': False, 'auth': self.auth,
                  'data': _body, 'headers': _headers}

        state, content = self.do_request('post', [202], params)
        return state

    def admin_role(self):
        set_role = False

        if not self.admin_role_state():
            set_role = self.set_admin_role()

        return set_role

    def cluster_state_name(self, cluster_name):
        state    = False
        path     = _deployment % _cluster % _info
        _url     = self._base_admin_url % (self._server, path)
        params   = {'url': _url, 'verify': False, 'auth': self.auth, 'headers': _headers}

        status_code, content = self.do_request('get', [200], params)

        if status_code == 200:
            state = (content['cluster_name'] == cluster_name)

        return state

    def configure_cluster(self, cluster_name):
        state    = False
        path     = _deployment % _cluster % _info
        _url     = self._base_admin_url % (self._server, path)
        body     = { 'cluster_name': cluster_name }
        _body    = self.body_to_json(body)

        params   = {'url': _url, 'verify': False, 'auth': self.auth,
                    'headers': _headers, 'data': _body}

        status_code, content = self.do_request('put', [200], params)
        return state

    def configure_cluster_name(self, cluster_name):
        state = False
        if not self.cluster_state_name(cluster_name):
            state = self.configure_cluster(cluster_name)
        return state

    def slice_state_name(self):
        state  = False
        path   = _deployment % slice_
        _url   = self._base_admin_url % (self._server, path)
        params = {'url': _url, 'verify': False,
                  'auth': self.auth, 'headers': _headers}

        status_code, content = self.do_request('get', [200], params)

        if content['slice_name'] == self._server:
            state = True

        return state

    def configure_slice(self):
        state  = False
        path   = _deployment % _slice % self._server
        _url   = self._base_admin_url % (self._server, path)
        body   = {'slice_name': self._server }
        _body  = self.body_to_json(body)

        params = {'url': _url, 'verify': False, 'data': _body,
                  'auth': self.auth, 'headers': _headers}

        status_code, content = self.do_request('put', [200], params)

        state = self.slice_state_name()

        return state

    def configure_slice_name(self):
        state = False
        if not self.slice_state_name():
            state = self.configure_slice()
        return state

class VropsConfig(object):
    """
    """
    def __init__(self, module):
        """
        """
        super(VropsConfig, self).__init__()
        self.module       = module
        self.admin        = module.params['administrator']
        self.admin_pass   = module.params['password']
        self._server      = module.params['vrops_ip_addess']
        self._ntp_servers = module.params['ntp_servers']
        self.vrops_client = VropsRestClient(self.admin, self.admin_pass, self._server)

    def _fail(self, msg=None):
        """Fail from AnsibleModule
        :param msg: defaults to None
        """
        if not msg: msg = "General Error occured"
        self.module.fail_json(msg=msg)

    def state_exit_unchanged(self):
        """Returns changed result and msg"""
        changed = False
        result = None
        msg = "EXIT UNCHANGED"
        return changed, result, msg

    def state_delete(self):
        """Returns changed result msg"""
        changed = False
        result = None
        msg = "STATE DELETE"

        return changed, result, msg

    def state_create(self):
        """Returns changed result and msg"""
        changed = False
        result = None
        msg = "STATE CREATE"

        api_state = self.vrops_client.api_state()

        if not api_state:
            msg = "API should be ready but is not"
            self._fail(msg)

        if self.module.params['set_admin_pass']:
            admin_password_state = self.vrops_client.set_admin_init_password()

        if 'ntp_servers' in self.module.params:
            _ntp_state = self.vrops_client.configure_ntp(self._ntp_servers)

        admin_role    = self.vrops_client.admin_role()
        cluster_name  = self.vrops_client.configure_cluster_name(self.module.params['cluster_name'])
        slice_name    = self.vrops_client.configure_slice_name()

        return changed, result, msg

    def run_state(self):
        """Exit AnsibleModule after running state"""
        changed = False
        result = None
        msg = None

        desired_state = self.module.params['state']
        current_state = self.check_state()
        module_state = (desired_state == current_state)

        if module_state:
            changed, result, msg = self.state_exit_unchanged()

        if desired_state == 'absent' and current_state == 'present':
            changed, result, msg = self.state_delete()

        if desired_state == 'present' and current_state == 'absent':
            changed, result, msg = self.state_create()

        self.module.exit_json(changed=changed, result=result, msg=msg)

    def check_state(self):
        state = 'absent'
        return state


def main():
    argument_spec = dict(administrator=dict(required=True, type='str'),
                         password=dict(required=True, type='str', no_log=True),
                         set_admin_pass=dict(required=False, type='bool'),
                         vrops_ip_addess=dict(required=True, type='str'),
                         cluster_name=dict(required=False, type='str'),
                         ntp_servers=dict(required=False, type='list'),
                         state=dict(default='present', choices=['present', 'absent']),)

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=False)

    if not IMPORTS:
        module.fail_json(msg="Failed to import modules")

    vrops = VropsConfig(module)
    vrops.run_state()


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
