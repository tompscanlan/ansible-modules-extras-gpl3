#!/usr/bin/python

try:
    from keystoneclient.v2_0 import client as ks_client
    HAS_CLIENTS = True
except ImportError:
    HAS_CLIENTS = False


def keystone_auth(module):

    ksclient = None

    try:
        ksclient = ks_client.Client(username=module.params['username'],
                                    password=module.params['password'],
                                    tenant_name=module.params['tenant_name'],
                                    auth_url=module.params['auth_url'],
                                    insecure=True)
    except Exception as e:
        module.fail_json(msg="Failed to get keystone client authentication: {}".format(e))

    return ksclient


def state_exit_unchanged(module):

    ks = keystone_auth(module)

    user = get_user(ks, module)[0]

    module.exit_json(changed=False,
                     user_name=user.name,
                     user_id=user.id)


def state_delete_user(module):
    module.exit_json(changed=False, msg="Delete User - not supported")


def state_create_user(module):

    ks = keystone_auth(module)

    project_name = module.params['project_name']

    tenant = [t for t in ks.tenants.list() if t.name == project_name][0]

    new_user = ks.users.create(name=module.params['new_user_name'],
                               password=module.params['new_user_pass'],
                               tenant_id=tenant.id)

    module.exit_json(changed=True,
                     user_name=new_user.name,
                     user_id=new_user.id)


def get_user(ks, module):

    user = [u for u in ks.users.list() if u.name == module.params['new_user_name']]

    if not user:
        user = None

    return user


def check_user_state(module):

    ks = keystone_auth(module)

    project = [p for p in ks.tenants.list() if p.name == module.params['project_name']]

    if not project:
        module.fail_json(msg="Failed getting project: {}".format(module.params['project_name']))

    user = get_user(ks, module)

    if not user:
        return 'absent'
    else:
        return 'present'


def main():
    argument_spec = dict(
        auth_url=dict(required=True, type='str'),
        username=dict(required=True, type='str'),
        password=dict(required=True, type='str'),
        tenant_name=dict(required=True, type='str'),
        project_name=dict(required=True, type='str'),
        new_user_name=dict(required=True, type='str'),
        new_user_pass=dict(required=True, type='str'),
        state=dict(default='present', choices=['present', 'absent'], type='str'),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)

    if not HAS_CLIENTS:
        module.fail_json(msg='python-keystone is required for this module')

    try:
        user_states = {
            'absent': {
                'present': state_delete_user,
                'absent': state_exit_unchanged,
            },
            'present': {
                'present': state_exit_unchanged,
                'absent': state_create_user,
            }
        }

        user_states[module.params['state']][check_user_state(module)](module)

    except Exception as e:
        module.fail_json(msg=str(e))


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()