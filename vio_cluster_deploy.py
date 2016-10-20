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
module: vio_deploy
short_description: Deploy vio cluster for chaperone vio
description:
    deploy/deletes vio cluster
Tested:
    - vsphere 6.0.0 Build 3632585
    - ansible 2.x
    - VIO 3.0
credits: Much thanks to VMware VIO Team for creating the omsclient
requirements:
    - json
    - logging
    - requests
    - inspect
options:
    oms_server:
        description:
            - IP of the oms on the management network
        required: True
        type: str
    login:
        description:
            - username for the user on the oms server
        required: True
        type: str
    password:
        description:
            - password for the oms server
        required: True
        type: str
    cluster_spec_json:
        description:
            - path to the vio cluster specification json file.
        required: True
        type: str
    state:
        description:
            - desired state of the vio cluster
        choices: present, absent 
'''

EXAMPLE = '''
- name: Kick off VIO Deployment
  vio_cluster_deploy:
    oms_server: "{{ vio_oms_ip_address }}"
    login: "{{ vio_oms_vcenter_username }}"
    password: "{{ vio_oms_vcenter_pwd }}"
    cluster_spec_json: "{{ vio_cluster_spec }}"
    vio_deployment_name: "{{ vio_cluster_name }}"
    state: 'present'
  tags:
    - vio_cluster
'''

try:
    import json
    import os
    import logging
    import requests
    import inspect
    IMPORTS = True
except ImportError:
    IMPORTS = False

LOG = logging.getLogger(__name__)
handler = logging.FileHandler('/tmp/vio_cluster_log.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
LOG.addHandler(handler)
LOG.setLevel(logging.DEBUG)

class RestClient(object):
    """OMS RestClient

    This is the client implementation based on "requests".
    """
    _URL_TEMPLATE_PREFIX = "https://%s:8443/oms/%s"

    def __init__(self, server, username, password):
        """Create a connection to the remote OMS server

        :param server: IP or hostname of the OMS server
        :param username: User name
        :param password: Password
        :return: None
        """
        self._server = server
        self._username = username
        self._password = password

        # TODO Do we need to have logout logic?
        self._session = self._login()

    def _api_url(self, path):
        api_url_template = "api/%s"
        api_path = api_url_template % path
        return self._URL_TEMPLATE_PREFIX % (self._server, api_path)

    def _login_url(self):
        login_url_template = \
            "j_spring_security_check?j_username=%s&j_password=%s"
        login_url = login_url_template % (self._username, self._password)
        return self._URL_TEMPLATE_PREFIX % (self._server, login_url)

    def _login(self):
        session = requests.Session()

        LOG.debug("Request login...")
        response = session.post(self._login_url(), verify=False)
        LOG.debug(response)

        return session

    def login(self):
        self._session = self._login()

    def do_get(self, path):
        url = self._api_url(path)

        LOG.debug("Request GET: %s" % url)
        response = self._session.get(url, verify=False)
        LOG.debug(response)

        return response

    def do_delete(self, path, object_id):
        url = self._api_url(path) + "/" + object_id

        LOG.debug("Request DELETE: %s" % url)
        response = self._session.delete(url, verify=False)
        LOG.debug(response)
        return response

    def do_post(self, path, data):
        url = self._api_url(path)
        headers = {'Content-type': 'application/json'}

        LOG.debug("Request POST: %s" % url)
        response = self._session.post(url, data, headers=headers, verify=False)
        LOG.debug(response)
        return response

    def do_put(self, path, data):
        url = self._api_url(path)
        headers = {'Content-type': 'application/json'}
        LOG.debug("Request PUT: %s" % url)

        response = self._session.put(url, data, headers=headers, verify=False)
        LOG.debug(response)
        return response


class OmsController(object):
    # Helper methods

    def __init__(self, oms, sso_user, sso_pwd):
        self.rest_client = RestClient(oms, sso_user, sso_pwd)
        self.logger = logging.getLogger(__name__)

        self._made_remote_dirs = []

    def login(self):
        self.rest_client.login()

    def hello(self):
        return self.rest_client.do_get('hello')

    def server_version(self):
        return self.rest_client.do_get('version')

    def server_status(self):
        return self.rest_client.do_get('status')

    def list_task(self):
        return self.rest_client.do_get('tasks')

    def list_networks(self):
        response = self.rest_client.do_get("networks")
        return response

    def list_datastores(self):
        response = self.rest_client.do_get("datastores")
        return response

    def list_deployments(self):
        clusters = self.rest_client.do_get('clusters')
        return clusters

    def list_deployment(self, name):
        api_url_template = "cluster/{}"
        url = api_url_template.format(name)
        cluster = self.rest_client.do_get(url)
        return cluster

    def delete_deployment(self, deployment_name):
        return self.rest_client.do_delete('cluster', deployment_name)

    def create_deployment_by_spec(self, deployment_json):
        resp = self._create_deployment(deployment_json)
        return resp

    def _create_deployment(self, spec):
        post_body = json.dumps(spec)
        resp = self.rest_client.do_post('clusters', post_body)
        return resp

    def add_compute_vc(self, spec):
        post_body = json.dumps(spec)
        resp = self.rest_client.do_post('vc', post_body)
        return resp

    def get_vc_ip(self):
        resp = self.rest_client.do_get('vcip')
        return resp

    def cluster_config(self, spec):
        resp = self.rest_client.do_put("cluster/VIO/config", spec)
        return resp

    def get_task(self, taskid):
        task = self.rest_client.do_get('task/{}'.format(taskid))
        return json.loads(task.text)

    def del_nova_datastore(self, spec):
        resp = self.rest_client.do_put("clusters/VIO/novadatastore", spec)
        return resp

    def del_glance_datastore(self, spec):
        resp = self.rest_client.do_put("clusters/VIO/glancedatastore", spec)
        return resp

    def retry_cluster(self, cluster, spec):
        api_url_template = "clusters/%s?action=retry"
        url = api_url_template % cluster
        put_body = json.dumps(spec)
        resp = self.rest_client.do_put(url, put_body)
        return resp

    def retrieve_cluster_profile(self, cluster):
        api_url_template = "clusters/%s/profile"
        url = api_url_template % cluster
        resp = self.rest_client.do_get(url)
        return resp

    def create_deployment_plan(self, spec):
        resp = self.rest_client.do_put("clusters/plan", spec)
        return resp

    def add_nova_node_plan(self, cluster, ng):
        api_url_template = "cluster/{}/nodegroup/{}/plan"
        url = api_url_template.format(cluster, ng)
        resp = self.rest_client.do_put(url, str(2))  # totalInstanceNum
        return resp

    def add_nova_node(self, cluster, ng, spec):
        api_url_template = "cluster/{}/nodegroup/{}/scaleout"
        url = api_url_template.format(cluster, ng)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def add_node_group(self, cluster, spec):
        api_url_template = "clusters/{}/nodegroups"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_post(url, spec)
        return resp

    def del_nova_node(self, cluster, ng, nd):
        api_url_template = "cluster/{}/nodegroup/{}/node"
        url = api_url_template.format(cluster, ng)
        resp = self.rest_client.do_delete(url, nd)
        return resp

    def increase_ips(self, nw, spec):
        api_url_template = "network/{}"
        url = api_url_template.format(nw)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def update_dns(self, nw, spec):
        api_url_template = "network/{}/async"
        url = api_url_template.format(nw)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def get_sysconf(self):
        resp = self.rest_client.do_get("conf")
        return json.loads(resp.text)

    def set_syslogserver(self, logserver, port, protocol, tag):
        url = \
            'conf?syslogserver={}&syslogserverport={}' \
            '&syslogserverprotocol={}&syslogservertag={}'
        resp = self.rest_client.do_put(
            url.format(
                logserver, port, protocol, tag), "")
        return resp

    def get_network_by_name(self, networkname):
        resp = self.rest_client.do_get("network/{}".format(networkname))
        return json.loads(resp.text)

    def create_support_bundle(self, spec):
        resp = self.rest_client.do_post("bundles", spec)
        return resp

    def get_support_bundle(self, spec, dest):
        resp = self.rest_client.do_post("bundles", spec)
        fileName = resp.text.split('/')[-1][0:-1]
        with open('%s/%s' % (dest, fileName), 'wb') as handle:
            resp = self.rest_client.do_get("bundle/{}".format(fileName))
            for block in resp.iter_content(1024):
                if not block:
                    break
                handle.write(block)
        return fileName

    def validate(self, type, spec):
        api_url_template = "validators/{}"
        url = api_url_template.format(type)
        put_body = json.dumps(spec)
        resp = self.rest_client.do_post(url, put_body)
        return resp

    def manage_openstack_services(self, cluster, service, action):
        api_url_template = "clusters/{}/services/{}?action={}"
        url = api_url_template.format(cluster, service, action)
        resp = self.rest_client.do_put(url, None)
        return resp

    def start_services(self, cluster, spec):
        api_url_template = "clusters/{}/services?action=start"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def stop_services(self, cluster, spec):
        api_url_template = "clusters/{}/services?action=stop"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def restart_services(self, cluster, spec):
        api_url_template = "clusters/{}/services?action=restart"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_put(url, spec)
        return resp

    def generate_csr(self, clusterName, spec):
        api_url_template = "clusters/{}/csr"
        url = api_url_template.format(clusterName)
        resp = self.rest_client.do_post(url, spec)
        return resp

    def add_horizon(self, cluster, spec):
        api_url_template = "clusters/{}/horizon"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_post(url, spec)
        return resp

    def del_horizon(self, cluster, title):
        api_url_template = "clusters/{}/horizon"
        url = api_url_template.format(cluster)
        resp = self.rest_client.do_delete(url, title)
        return resp

    def list_horizon(self, cluster):
        api_url_template = "clusters/{}/horizon"
        url = api_url_template.format(cluster)
        regions = self.rest_client.do_get(url)
        return regions

    def get_plugin_status(self):
        url = "plugin/status"
        resp = self.rest_client.do_get(url)
        return resp

    def check_oms_vc_connection(self):
        url = "checkOmsVCConnection"
        resp = self.rest_client.do_get(url)
        return resp

    def get_oms_vc_status(self):
        url = "connection/status"
        resp = self.rest_client.do_get(url)
        return resp

    def register_plugin(self):
        url = "plugin/register?addException=true"
        resp = self.rest_client.do_post(url, "")
        return resp

    def change_datacollector_setting(self, enable="false"):
        api_url_template = "datacollector?enabled={}"
        url = api_url_template.format(enable)
        resp = self.rest_client.do_post(url, "")
        return resp

    def get_datacollector_setting(self):
        url = "datacollector"
        resp = self.rest_client.do_get(url)
        return resp

    def get_audit_file(self):
        url = "phauditfile"
        resp = self.rest_client.do_get(url)
        return resp

    def start_cluster(self, cluster):
        api_url_template = "cluster/%s?action=start"
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return resp

    def stop_cluster(self, cluster):
        api_url_template = "cluster/%s?action=stop"
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return resp

    def upgrade_provision(self, cluster, spec):
        post_body = json.dumps(spec)
        api_url_template = '/clusters/%s/upgrade/provision'
        url = api_url_template % cluster
        resp = self.rest_client.do_post(url, post_body)
        return resp

    def upgrade_retry(self, cluster, spec):
        put_body = json.dumps(spec)
        api_url_template = '/clusters/%s/upgrade/retry'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, put_body)
        return resp

    def upgrade_migrate_data(self, cluster):
        api_url_template = '/clusters/%s/upgrade/configure'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return resp

    def upgrade_switch_to_green(self, cluster):
        api_url_template = '/clusters/%s/upgrade/switch'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, "")
        return resp

    def switch_keystone_backend(self, cluster, spec):
        put_body = json.dumps(spec)
        api_url_template = '/clusters/%s/keystonebackend'
        url = api_url_template % cluster
        resp = self.rest_client.do_put(url, put_body)
        return resp


def log(message=None):
    func = inspect.currentframe().f_back.f_code
    msg="Method: {} Line Number: {} Message: {}".format(func.co_name, func.co_firstlineno, message)
    LOG.debug(msg)


class OmsDeploy(object):
    """OmsDeploy"""
    def __init__(self, module):
        self.module = module
        self.server = module.params['oms_server']
        self.user = module.params['login']
        self.password = module.params['password']
        self.cluster_name = module.params['vio_deployment_name']
        self.cluster_spec_file = module.params['cluster_spec_json']
        self.desired_state = module.params['state']
        self.oms = OmsController(self.server, self.user, self.password)

    def _parse_response(self, response, key):
        resp_content = json.loads(response.content)
        try:
            target = [v for k, v in resp_content.iteritems() if k == key][0]
        except KeyError as e:
            self.module.fail_json(msg="KeyError: {}".format(e))
        return target

    def oms_status(self, key, state):
        log()
        resp = self.oms.get_oms_vc_status()
        if resp.status_code != 200:
            msg="Response: {}".format(resp.status_code)
            log(msg)
            self.module.fail_json(msg=msg)
        resp_content = self._parse_response(resp, key)
        log(resp_content)
        return resp_content

    def oms_vc_reachable(self):
        log()
        return self.oms_status('oms.vc.reachable', 'true')

    def oms_vapp_need_restart(self):
        log()
        return self.oms_status('oms.need.restart.vapp', 'false')

    def oms_ext_registered(self):
        log()
        return self.oms_status('oms.extension.registered', 'true')

    def oms_vc_connection_status(self):
        log()
        connection_status = self.oms.check_oms_vc_connection()

        if connection_status.status_code != 200:
            msg="Failed to get connection status"
            log(msg)
            self.module.fail_json(msg=msg)
        if json.loads(connection_status.content) != 'success':
            state = False
        else:
            state = True
        log(state)
        return state

    def oms_plugin_state(self):
        log()
        resp = self.oms.get_plugin_status()
        if resp.status_code != 200:
            self.module.fail_json(msg="Failed to get plugin status")
        log(json.loads(resp.content))
        return json.loads(resp.content)

    def deployments(self):
        log()
        deployments = self.oms.list_deployments()
        if deployments.status_code != 200:
            msg="Failed to get deployments"
            log(msg)
            self.module.fail_json(msg="Failed to get deployments")
        log(deployments)
        return deployments

    def deployment_present(self, deployments):
        log()
        state = False
        deployment_list = json.loads(deployments.content)

        if not deployment_list:
            return False
        try:
            deployment_name = [v for i in deployment_list for k, v in i.iteritems() if k == 'name'][0]
        except KeyError as k:
            msg=msg="KeyError checking deployment: {}".format(k)
            log(msg)
            self.module.fail_json(msg=msg)

        if deployment_name == self.cluster_name:
            state = True
        log(state)
        return state

    def get_deployment_status(self, deployments):
        log()
        deploy_list = json.loads(deployments.content)
        status = [v for i in deploy_list for k, v in i.iteritems() if k == 'status'][0]
        log(status)
        return status

    def spec_json_data(self):
        log()
        try:
            with open(self.cluster_spec_file) as json_data:
                cluster_spec = json.load(json_data)
        except Exception as e:
            msg="Invalid json: {}".format(e)
            log(msg)
            self.module.fail_json(msg=msg)
        log(cluster_spec)
        return cluster_spec

    def create_plan(self):
        log()
        json_data = self.spec_json_data()
        data = json.dumps(json_data)
        plan = self.oms.create_deployment_plan(data)
        if plan.status_code != 200:
            msg="Failed to create plan: {}".format(plan.status_code)
            log(msg)
            self.module.fail_json(msg=msg)
        json_data['attributes']['attributes'] = plan.content
        log(json_data)
        return json_data

    def state_create_deployment(self):
        log()
        plan = self.create_plan()
        create = self.oms.create_deployment_by_spec(plan)
        log(create.status_code)

        if create.status_code != 202:
            msg="Failed to deploy cluster status code: {}".format(create.status_code)
            log(msg)
            self.module.fail_json(msg=msg)

        self.module.exit_json(changed=True, result=create.status_code)

    def check_deployment_state(self):
        log()
        if not self.oms_vc_reachable():
            msg="Oms cannot reach VC"
            log(msg)
            self.module.fail_json(msg=msg)
        if not self.oms_ext_registered():
            msg="Oms extention not registered"
            log(msg)
            self.module.fail_json(msg=msg)
        if not self.oms_vc_connection_status():
            msg="Oms not connetect"
            log(msg)
            self.module.fail_json(msg=msg)

        deployments = self.deployments()

        if self.deployment_present(deployments):
            deploy_status = self.get_deployment_status(deployments)
            if deploy_status == 'PROVISION_ERROR':
                return 'update'
            elif deploy_status in ['PROVISIONING', 'RUNNING']:
                return 'present'
        else:
            return 'absent'

    def state_exit_unchanged(self):
        self.module.exit_json(msg="EXIT UNCHANGED")

    def delete_deployment(self):
        log()
        delete_deploy = self.oms.delete_deployment(self.cluster_name)
        if delete_deploy.status_code != 202:
            msg="Failed deleting deployment: {}".format(delete_deploy.status_code)
            log(msg)
            self.module.fail_json(msg=msg)
        log(delete_deploy.status_code)
        self.module.exit_json(changed=True, result=delete_deploy.status_code)

    def state_update_deployment(self):
        self.module.exit_json(msg="update")

    def process_state(self):
        states = {
            'absent': {
                'update': self.delete_deployment,
                'present': self.delete_deployment,
                'absent': self.state_exit_unchanged,
            },
            'present': {
                'update': self.state_update_deployment,
                'present': self.state_exit_unchanged,
                'absent': self.state_create_deployment,
            }
        }

        current_state = self.check_deployment_state()
        states[self.desired_state][current_state]()


def main():
    argument_spec = dict(
        oms_server=dict(required=True, type='str'),
        login=dict(required=True, type='str'),
        password=dict(required=True, type='str', no_log=True),
        cluster_spec_json=dict(required=True, type='str'),
        vio_deployment_name=dict(required=True, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not IMPORTS:
        module.fail_json(msg='python modules failed to import required for this module')

    oms_deploy = OmsDeploy(module)
    oms_deploy.process_state()


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()