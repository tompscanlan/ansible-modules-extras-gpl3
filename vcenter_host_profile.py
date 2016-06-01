#!/usr/bin/python
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
module: vcenter_host_profile
short_description: creates updates deletes host profiles
description:
    creates updates deletes host profiles.
notes:
    requirements: ansible 2.x
    - Tested on vSphere 6.0
options:
    hostname:
        description:
            - The hostname or IP address of the vSphere vCenter API server
        required: True
    username:
        description:
            - The username of the vSphere vCenter
        required: True
        aliases: ['user', 'admin']
    password:
        description:
            - The password of the vSphere vCenter
        required: True
        aliases: ['pass', 'pwd']
    esxi_hostname:
        description:
            - The esxi host to extract the host profile from
    state:
        description:
            - desired state
        choices: ['present', 'absent']
        required: True
'''

EXAMPLES = '''
- name: Host Profile
  vcenter_host_profile:
    hostname: "{{ vcenter }}"
    username: "{{ vcenter_user }}"
    password: "{{ vcenter_password }}"
    validate_certs: "{{ vcenter_validate_certs }}"
    esxi_hostname: "{{ item }}"
    state: 'absent'
  with_items:
    - "{{ host_profile }}"
  tags:
    - taghere
'''

try:
    from pyVmomi import vim, vmodl
    import datetime
    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False


vc = {}


def get_host_profile(si, profilename):

    profile = None

    profiles = si.hostProfileManager.profile

    for p in profiles:
        if p.name == profilename:
            profile = p

    return profile


def profile_spec(name, host):

    spec = vim.profile.host.HostProfile.HostBasedConfigSpec(
        name = name,
        enabled = True,
        host = host,
        useHostProfileEngine = True,
    )

    return spec


def create_profile(module, si, spec):

    host_profile = None

    profile_manager = si.hostProfileManager

    try:
        host_profile = profile_manager.CreateProfile(spec)
    except Exception as e:
        module.fail_json(msg="Failed to create host profile: {}".format(str(e)))

    return host_profile


def update_reference_host(module, profile, host):

    state = False

    try:
        profile.UpdateReferenceHost(host)
        state = True
    except Exception as e:
        module.fail_json(msg="Failed to update reference host: {}".format(str(e)))

    return state


def check_host_profile(si, host, profile_name, present):

    state = False

    profile_manager = si.hostProfileManager

    profiles = [p for p in profile_manager.profile]

    if not profiles:
        return False

    if present:
        for profile in profiles:
            if profile.name == profile_name:
                state = True

    if not present:
        for p in profiles:
            if p.name == profile_name:
                if p.referenceHost == host:
                    state = True

    return state


def profile_name(cluster_name):

    fmt = '%Y_%m_%d'
    time_stamp = datetime.datetime.now().strftime(fmt)

    sep = "_"
    seq = (cluster_name, time_stamp)

    profilename = sep.join(seq)

    return profilename


def state_create_profile(module):

    changed = False
    result = None

    si = vc['si']
    host = vc['host']
    profile_name = vc['profile_name']

    spec = profile_spec(profile_name, host)

    profile = create_profile(module, si, spec)

    if not profile:
        module.fail_json(msg="Failed creating profile")

    update_ref_host = update_reference_host(module, profile, host)

    if update_ref_host:
        changed = True
        result = profile.name

    module.exit_json(changed=changed, result=result)


def state_update_profile(module):

    profilename = vc['profile_name']
    si = vc['si']
    host = vc['host']

    profile = get_host_profile(si, profilename)

    if not profile:
        module.fail_json(msg="Failed to get profile to update ref host")

    changed = update_reference_host(module, profile, host)

    if not changed:
        module.fail_json(msg="Failed to update ref host for host profile")

    module.exit_json(changed=changed)


def state_destroy_profile(module):

    profilename = vc['profile_name']
    si = vc['si']

    profile = get_host_profile(si, profilename)

    if not profile:
        module.fail_json(msg="Failed to get profile to update ref host")

    try:
        profile.DestroyProfile()
    except Exception as e:
        module.exit_json(msg="Failed to destroy profile: {}".format(str(e)))

    module.exit_json(changed=True)


def state_exit_unchanged(module):
    module.exit_json(changed=False, msg="EXIT UNCHANGED")


def check_profile_state(module):

    esxi_hostname = module.params['esxi_hostname']

    si = connect_to_api(module)

    vc['si'] = si

    host = find_hostsystem_by_name(si, esxi_hostname)

    if not host:
        module.fail_json(msg="Failed getting host: {}".format(esxi_hostname))

    vc['host'] = host
    vc['profile_name'] = profile_name(host.parent.name)

    profile_present = check_host_profile(si, host, vc['profile_name'], True)

    if not profile_present:
        return 'absent'

    profile_config = check_host_profile(si, host, vc['profile_name'], False)

    if not profile_config:

        return 'update'

    return 'present'



def main():
    argument_spec = vmware_argument_spec()

    argument_spec.update(
        dict(
            esxi_hostname=dict(required=True, type='str'),
            state=dict(required=True, choices=['present', 'absent'], type='str'),
        )
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_PYVMOMI:
        module.fail_json(msg='pyvmomi is required for this module')

    try:
        profile_states = {
            'absent': {
                'absent': state_exit_unchanged,
                'present': state_destroy_profile,
            },
            'present': {
                'present': state_exit_unchanged,
                'update': state_update_profile,
                'absent': state_create_profile,
            }
        }

        profile_states[module.params['state']][check_profile_state(module)](module)

    except vmodl.RuntimeFault as runtime_fault:
        module.fail_json(msg=runtime_fault.msg)
    except vmodl.MethodFault as method_fault:
        module.fail_json(msg=method_fault.msg)
    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *
from ansible.module_utils.vmware import *

if __name__ == '__main__':
    main()